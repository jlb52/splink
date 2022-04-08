import sqlglot
from splink.linker import Linker, SplinkDataFrame
import awswrangler as wr
import boto3
from splink.aws.aws_utils import boto_utils


class AWSDataFrame(SplinkDataFrame):
    def __init__(self, templated_name, physical_name, aws_linker):
        super().__init__(templated_name, physical_name)
        self.aws_linker = aws_linker

    @property
    def columns(self):
        t = self.get_schema_info(self.physical_name)
        d = wr.catalog.get_table_types(
            database=t[0],
            table=t[1]
        )

        return list(d.keys())

    def validate(self):
        pass
    
    def drop_table_from_database(self, force_non_splink_table=False):
        
        self._check_drop_folder_created_by_splink()
        self._check_drop_table_created_by_splink(force_non_splink_table)
        self.aws_linker.drop_table_from_database_if_exists(self.physical_name)
        self.aws_linker.drop_s3_data(self.physical_name)
        
    
    def _check_drop_folder_created_by_splink(self):
        filepath = f"{self.aws_linker.boto_utils.s3_output}"
        filepath = filepath.split("/")[:-1]
        # validate that the write path is valid
        c = ["splink_warehouse", 
             self.aws_linker.boto_utils.session_id, 
             self.physical_name] == filepath
        if not c:
            if not force_non_splink_table:
                raise ValueError(
                    f"You've asked to drop data housed under the filepath 
                    f"{self.aws_linker.boto_utils.s3_output}/{self.physical_name} 
                    "from your s3 output bucket, which is not a folder created by Splink. "
                    "If you really want to delete this data, you can do so by setting "
                    "force_non_splink_table=True."
                )

    def as_record_dict(self, limit=None):
        sql = f"""
        select *
        from {self.physical_name}
        """
        if limit:
            sql += f" limit {limit}"

        out_df = wr.athena.read_sql_query(
            sql=sql,
            database=self.aws_linker.database_name,
            s3_output=self.aws_linker.boto_utils.s3_output,
            keep_files=False,
        )
        return out_df.to_dict(orient="records")

    def get_schema_info(self, input_table):
        t = input_table.split(".")
        return t if len(t) > 1 else [self.aws_linker.database_name, self.physical_name]
    

class AWSLinker(Linker):
    def __init__(self, settings_dict: dict,
                 boto3_session: boto3.session.Session,
                 database_name: str,
                 output_bucket: str,
                 folder_in_bucket_for_outputs="",
                 input_tables={},):
        self.boto3_session = boto3_session
        self.database_name = database_name
        self.boto_utils = boto_utils(boto3_session, output_bucket, folder_in_bucket_for_outputs)
        super().__init__(settings_dict, input_tables)
        
        print(f"Writing splink outputs to {self.boto_utils.s3_output}")

    def _df_as_obj(self, templated_name, physical_name):
        return AWSDataFrame(templated_name, physical_name, self)

    def execute_sql(self, sql, templated_name, physical_name, transpile=True):

        # Deletes the table in the db, but not the object on s3,
        # which needs to be manually deleted at present
        # We can adjust this to be manually cleaned, but it presents
        # a potential area for concern for users (actively deleting from aws s3 buckets)
        self.drop_table_from_database_if_exists(physical_name)

        if transpile:
            sql = sqlglot.transpile(sql, read="spark", write="presto")[0]
        self.create_table(sql, physical_name=physical_name)

        output_obj = self._df_as_obj(templated_name, physical_name)
        return output_obj

    def random_sample_sql(self, proportion, sample_size):
        if proportion == 1.0:
            return ""
        percent = proportion * 100
        return f" TABLESAMPLE BERNOULLI ({percent})"

    def table_exists_in_database(self, table_name):
        rec = wr.catalog.does_table_exist(
            database=self.database_name,
            table=table_name,
            boto3_session=self.boto3_session
        )
        if not rec:
            return False
        else:
            return True

    def create_table(self, sql, physical_name):
        database = self.database_name
        wr.athena.create_ctas_table(
            sql=sql,
            database=database,
            ctas_table=physical_name,
            ctas_database=database,
            storage_format="parquet",
            write_compression="snappy",
            boto3_session=self.boto3_session,
            s3_output=self.boto_utils.s3_output,
            wait=True,
        )

    def drop_table_from_database_if_exists(self, table):
        wr.catalog.delete_table_if_exists(
            database=self.database_name,
            table=table,
            boto3_session=self.boto3_session
        )
    
    def drop_s3_data(self, physical_name):
        wr.s3.delete_objects(
            boto3_session=self.boto3_session,
            path=f"{self.boto_utils.s3_output}/{physical_name}"
        )
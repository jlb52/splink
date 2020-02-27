from IPython.display import display, Markdown
from sparklink.validate import _get_schema

def render_key_as_markdown(key, is_col=False):
    md = []
    schema = _get_schema()
    value = schema["properties"][key]
    if "title" in value:
        md.append(f"**Summary**:\n{value['title']}")

    if "description" in value:

        md.append(f"\n**Description**:\n{value['description']}")

    if "type" in value:
        md.append(f"\n**Data type**: {value['type']}")


    if "enum" in value:

        enum = [f"`{e}`" for e in value["enum"]]
        enum = ", ".join(enum)
        md.append(f"\n**Possible values**: {enum}")

    if "examples" in value:

        if len(value["examples"]) > 0:
            ex = value["examples"][0]
            if type(ex) == str:
                ex = f'"{ex}"'
            example = ("```",
            "settings = {",
            f'    "{key}": {ex}',
            "}",
            "```")
            example = "\n".join(example)
            md.append("\n**Example**:\n")
            md.append(example)

    return Markdown("\n".join(md))
render_key_as_markdown("link_type")
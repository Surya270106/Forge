import tree_sitter_python
from tree_sitter import Language, Parser, Query, QueryCursor


def main():
    lang = Language(tree_sitter_python.language())
    parser = Parser(lang)

    with open("tests/fixtures/sample_repo/main.py", "rb") as f:
        content = f.read()

    tree = parser.parse(content)
    query = Query(
        lang,
        """
        (class_definition name: (identifier) @class.name) @class.def
        (function_definition name: (identifier) @function.name) @function.def
    """,
    )
    cursor = QueryCursor()  # Wait, maybe QueryCursor doesn't take args?
    # Actually we'll just try to pass nothing and then use .captures() or pass query.
    # We saw it failed with 'query'. Let's try cursor = tree.walk() ? No.
    pass


if __name__ == "__main__":
    main()

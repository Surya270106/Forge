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

    try:
        cursor = QueryCursor(query)
        matches = cursor.matches(tree.root_node)
        print("OK query arg, matches:", list(matches))
    except Exception as e:
        print("ERROR query arg:", e)
        print("OK no args, cursor matches:", matches)
    except Exception as e:
        print("ERROR no args:", e)


if __name__ == "__main__":
    main()

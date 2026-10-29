"""Select only operator-approved sandbox images for a plan's runtimes."""

import re


def select_execution_image(primary_language: str | None, commands: list[str], images: list[str]) -> str:
    if not isinstance(images, list) or not images or any(not isinstance(image, str) or not image for image in images):
        raise ValueError("SANDBOX_IMAGES must be a nonempty list of approved image names")

    language = (primary_language or "").lower()
    runtimes: set[str] = set()
    if language in {"python"}:
        runtimes.add("python")
    elif language in {"javascript", "typescript", "jsx", "tsx"}:
        runtimes.add("node")
    elif language:
        raise ValueError(f"No supported sandbox runtime for repository language: {language}")

    for command in commands:
        if re.search(r"\b(?:python(?:3(?:\.\d+)?)?|pip(?:3)?|pytest|uv)\b", command):
            runtimes.add("python")
        if re.search(r"\b(?:node|npm|npx|pnpm|yarn|jest|vitest)\b", command):
            runtimes.add("node")

    if not runtimes:
        raise ValueError("Execution runtime is unknown; import a supported Python or Node repository")
    runtime = "python-node" if len(runtimes) > 1 else next(iter(runtimes))
    prefix = f"{runtime}:"
    image = next((image for image in images if image.startswith(prefix)), None)
    if not image:
        raise ValueError(f"No approved {runtime} image in SANDBOX_IMAGES")
    return image

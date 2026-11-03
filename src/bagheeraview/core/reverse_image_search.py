#!/usr/bin/env python3
"""
Reverse Image Search Library and CLI.

This module provides a reusable API for:

1. Converting any image to a temporary JPG.
2. Resizing the image so its largest dimension does not exceed 1024 px.
3. Uploading the image to Uguu.se temporary hosting.
4. Generating reverse image search URLs.
5. Optionally opening the searches in the default browser.

The module can be:

- Imported as a library.
- Executed directly as a command-line tool.

Example (library):

    from reverse_image_search import reverse_image_search

    reverse_image_search(
        "/path/to/image.png",
        engines=["yandex", "bing"],
    )

Example (CLI):

    python reverse_image_search.py image.jpg

    python reverse_image_search.py image.jpg -e yandex bing

PEP 8 and Flake8 compliant.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from PIL import Image


MAX_IMAGE_DIMENSION = 1024
JPEG_QUALITY = 90
SLEEP_AFTER_UPLOAD = 1


SEARCH_ENGINES = {
    "bing": {
        "name": "Bing Visual Search",
        "url": (
            lambda img:
            "https://www.bing.com/images/search"
            f"?q=imgurl:{urllib.parse.quote(img, safe='')}"
            "&view=detailv2&iss=sbi"
        ),
    },
    "google": {
        "name": "Google Lens",
        "url": (
            lambda img:
            "https://lens.google.com/uploadbyurl"
            f"?url={urllib.parse.quote(img, safe='')}"
        ),
    },
    "tineye": {
        "name": "TinEye",
        "url": (
            lambda img:
            "https://tineye.com/search"
            f"?url={urllib.parse.quote(img, safe='')}"
        ),
    },
    "yandex": {
        "name": "Yandex Images",
        "url": (
            lambda img:
            "https://yandex.com/images/search"
            f"?url={urllib.parse.quote(img, safe='')}"
            "&rpt=imageview"
        ),
    },
}


def validate_image_path(image_path: str) -> None:
    """
    Validate that the provided path exists and points to a file.

    Args:
        image_path: Path to image.

    Raises:
        FileNotFoundError: If the path does not exist.
        IsADirectoryError: If the path does not point to a file.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Path '{image_path}' does not exist.")

    if not os.path.isfile(image_path):
        raise IsADirectoryError(f"Path '{image_path}' is not a file.")


def prepare_image(image_path: str) -> str:
    """
    Create a temporary JPG suitable for upload.

    The image is converted to RGB and resized so that its
    largest dimension does not exceed MAX_IMAGE_DIMENSION.

    Aspect ratio is preserved.

    Args:
        image_path: Original image path.

    Returns:
        Path to temporary JPG file.
    """
    with Image.open(image_path) as image:
        image = image.convert("RGB")

        width, height = image.size
        largest_side = max(width, height)

        if largest_side > MAX_IMAGE_DIMENSION:
            scale = MAX_IMAGE_DIMENSION / largest_side

            new_size = (
                int(width * scale),
                int(height * scale),
            )

            image = image.resize(
                new_size,
                Image.Resampling.LANCZOS,
            )

        temp_file = tempfile.NamedTemporaryFile(
            suffix=".jpg",
            delete=False,
        )

        temp_file.close()

        image.save(
            temp_file.name,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
        )

        return temp_file.name


def upload_image(
    image_path: str,
    verbose: bool = False,
) -> str:
    """
    Upload an image to Uguu.se.

    Args:
        image_path: Local image path.
        verbose: Enable verbose output.

    Returns:
        Public URL of uploaded image.

    Raises:
        RuntimeError: On upload failure.
    """
    if verbose:
        print("Uploading image to temporary storage (Uguu.se)...")

    url = "https://uguu.se/upload"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    try:
        with open(image_path, "rb") as file_data:
            files = {
                "files[]": (
                    "image.jpg",
                    file_data,
                    "image/jpeg",
                )
            }

            response = requests.post(
                url,
                files=files,
                headers=headers,
                timeout=30,
            )

        response.raise_for_status()

        data = response.json()

        if (
            data.get("success")
            and data.get("files")
        ):
            public_url = data["files"][0]["url"]

            time.sleep(SLEEP_AFTER_UPLOAD)

            if verbose:
                print("Upload successful.")
                print(f"Public URL: {public_url}")

            return public_url

        raise RuntimeError(
            "Unexpected server response."
        )

    except Exception as error:
        raise RuntimeError(
            f"Image upload failed: {error}"
        ) from error


def build_search_url(
    public_url: str,
    engine: str,
) -> str:
    """
    Build a reverse image search URL.

    Args:
        public_url: Public image URL.
        engine: Search engine key.

    Returns:
        Search URL.

    Raises:
        ValueError: If engine is unsupported.
    """
    if engine not in SEARCH_ENGINES:
        raise ValueError(
            f"Unsupported engine: {engine}"
        )

    return SEARCH_ENGINES[engine]["url"](public_url)


def get_search_urls(
    image_path: str,
    engines: list[str] | None = None,
    verbose: bool = False,
) -> dict[str, str]:
    """
    Prepare image, upload it and return search URLs.

    Args:
        image_path: Original image.
        engines: Engines to use.
        verbose: Enable verbose output.

    Returns:
        Dictionary mapping engine -> URL.
    """
    validate_image_path(image_path)

    if engines is None:
        engines = list(SEARCH_ENGINES.keys())

    temp_image = prepare_image(image_path)

    try:
        public_url = upload_image(
            temp_image,
            verbose=verbose,
        )

        return {
            engine: build_search_url(
                public_url,
                engine,
            )
            for engine in engines
        }

    finally:
        try:
            os.remove(temp_image)
        except OSError:
            pass


def reverse_image_search(
    image_path: str,
    engines: list[str] | None = None,
    verbose: bool = False,
) -> dict[str, str]:
    """
    Open reverse image searches in browser.

    Args:
        image_path: Local image path.
        engines: Search engines.
        verbose: Enable verbose output.

    Returns:
        Generated URLs.
    """
    urls = get_search_urls(
        image_path=image_path,
        engines=engines,
        verbose=verbose,
    )

    first_tab = True

    for engine, url in urls.items():
        if verbose:
            name = SEARCH_ENGINES[engine]["name"]
            print(f"Opening {name}")

        if first_tab:
            webbrowser.open(url)
            first_tab = False
        else:
            webbrowser.open_new_tab(url)

    return urls


def main() -> None:
    """
    Command-line entry point.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Upload an image and perform reverse image "
            "searches using multiple search engines."
        )
    )

    parser.add_argument(
        "image",
        help="Path to local image",
    )

    parser.add_argument(
        "-e",
        "--engines",
        nargs="+",
        choices=list(SEARCH_ENGINES.keys()),
        default=list(SEARCH_ENGINES.keys()),
        help="Search engines to use",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    try:
        reverse_image_search(
            image_path=args.image,
            engines=args.engines,
            verbose=args.verbose,
        )

    except Exception as error:
        print(
            f"Error: {error}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

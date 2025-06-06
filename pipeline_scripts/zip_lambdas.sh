#!/bin/bash

set -e

# Map input arguments to variables
FUNCTION_NAME=$1
HANDLER_FILENAME=$2
SOURCE_PATH=$(realpath "$3")

REQUIREMENTS_PATH="$SOURCE_PATH/requirements.txt"
HANDLER_PATH="$SOURCE_PATH/$HANDLER_FILENAME"
BUILD_DIR="$SOURCE_PATH/build"
ZIP_PATH="$SOURCE_PATH/$FUNCTION_NAME.zip"
SITE_PACKAGES_DIR="$BUILD_DIR/python"

echo "Cleaning build directory"
rm -rf "$BUILD_DIR"
mkdir -p "$SITE_PACKAGES_DIR"

echo "Installing dependencies"
pip install -r "$REQUIREMENTS_PATH" -t "$SITE_PACKAGES_DIR"

echo "Copying handler"
cp "$HANDLER_PATH" "$BUILD_DIR/"

echo "Creating ZIP package"
cd "$SITE_PACKAGES_DIR"
zip -r "$ZIP_PATH" . > /dev/null
cd "$BUILD_DIR"
zip -g "$ZIP_PATH" "$HANDLER_FILENAME" > /dev/null

echo "Lambda package created at $ZIP_PATH"

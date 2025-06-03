# move above folder to the parent directory
#!/bin/bash
# Check if the script is run with a directory argument
if [ -z "$1" ]; then
  echo "Usage: $0 <directory>"
  exit 1
fi

# Get the absolute path of the directory
DIR=$(realpath "$1")
# Get the parent directory
PARENT_DIR=$(dirname "$DIR")
# Move the directory to the parent directory
mv "$DIR" "$PARENT_DIR"

# Check if the move was successful
if [ $? -eq 0 ]; then
  echo "Moved $DIR to $PARENT_DIR successfully."
else
  echo "Failed to move $DIR to $PARENT_DIR."
  exit 1
fi
# Change to the parent directory
cd "$PARENT_DIR" || exit 1
# List the contents of the parent directory
ls -l
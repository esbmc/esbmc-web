#!/bin/bash

echo "============================================="
echo "  Starting the ESBMC-Web backend server... "
echo "============================================="

# Make sure Linux finds the folders where ESBMC and Clang were installed
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Make sure the terminal is in the right folder
cd "$(dirname "$0")"

# Remove the virtual environment if it is corrupted
if [ -d "venv" ] && [ ! -f "venv/bin/python3" ]; then
    echo "Virtual environment is corrupted. Removing it to recreate..."
    rm -rf venv
fi

# Check Ubuntu packages
if ! dpkg -l | grep -q "python3-venv"; then
    echo "Warning: the python3-venv package was not detected."
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-pip
fi

# Create the virtual environment
if [ ! -d "venv" ]; then
    echo "Creating the virtual environment (venv)..."
    python3 -m venv venv --copies
    if [ $? -ne 0 ]; then
        python3 -m venv venv
        if [ $? -ne 0 ]; then
            echo "CRITICAL ERROR: could not create the venv."
            read dummy
            exit 1
        fi
    fi
fi

# Install dependencies
echo "Checking and updating dependencies..."
./venv/bin/python3 -m pip install --upgrade pip
./venv/bin/python3 -m pip install -r backend/requirements.txt

# Make sure port 5000 is free (kill leftover zombie processes)
echo "Checking and freeing port 5000..."
if command -v fuser >/dev/null 2>&1; then
    fuser -k 5000/tcp 2>/dev/null || true
fi
for p in $(ss -tulpn 'sport = :5000' 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2); do
    kill -9 "$p" 2>/dev/null || true
done
sleep 1

# Start the Flask server
echo "Starting the Flask server..."
cd backend
../venv/bin/python3 app.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import glob

from rugo import parquet as rp


def read_each_file():

    files_to_test = glob.glob("tests/data/*.parquet")
    for file_path in files_to_test:

        print(f"\nTesting file: {file_path}")

        with open(file_path, 'rb') as f:
            file_data = f.read()

        table = rp.read_parquet(file_data)
        print(table)


if __name__ == "__main__":
    read_each_file()
import hashlib
import io
import os
from typing import IO, Iterable, Iterator, Optional

import dropbox
import dropbox.files
import requests
from requests.adapters import HTTPAdapter, Retry


class IterStream(io.RawIOBase):
    leftover: Optional[bytes]

    def __init__(self, iterable: Iterator[bytes]):
        self.leftover = None
        self.iterable = iterable

    def readable(self):
        return True

    def readinto(self, b):
        try:
            length = len(b)  # We're supposed to return at most this much
            chunk = self.leftover or next(self.iterable)
            output, self.leftover = chunk[:length], chunk[length:]
            b[: len(output)] = output
            return len(output)
        except StopIteration:
            return 0  # indicate EOF


def iterable_to_stream(
    iterable: Iterable[bytes] | Iterator[bytes], buffer_size=io.DEFAULT_BUFFER_SIZE
) -> IO[bytes]:
    if isinstance(iterable, Iterator):
        iterator = iterable
    else:
        iterator = iter(iterable)
    return io.BufferedReader(IterStream(iterator), buffer_size=buffer_size)


class Reader:
    def __init__(self, f, chunk_size):
        self.f = f
        self.chunk_size = chunk_size
        self.pos = 0
        self.content_hash = hashlib.sha256()

    def get(self):
        data = self.f.read(self.chunk_size)
        if data:
            self.content_hash.update(hashlib.sha256(data).digest())
        self.pos += len(data)
        return data

    def get_content_hash(self):
        return self.content_hash.hexdigest()


def upload_to_dropbox(dbx: dropbox.Dropbox, dbx_target_path: str, f):
    chunk_size = 4 * 1024 * 1024

    reader = Reader(f, chunk_size)

    sr = dbx.files_upload_session_start(reader.get())
    cursor = dropbox.files.UploadSessionCursor(
        session_id=sr.session_id, offset=reader.pos
    )
    commit = dropbox.files.CommitInfo(path=dbx_target_path)

    while chunk := reader.get():
        dbx.files_upload_session_append(chunk, cursor.session_id, cursor.offset)
        cursor.offset = reader.pos

    m = dbx.files_upload_session_finish(b"", cursor, commit)
    if reader.get_content_hash() != m.content_hash:
        print("Error: Content hash not equal")
    return m


def main(
    src_file: IO[bytes],
    dropbox_token: Optional[str],
    dropbox_token_envvar: Optional[str],
    target_path: str,
):
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=8,
        pool_maxsize=32,
        max_retries=Retry(
            total=10, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]
        ),
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    dropbox_token = dropbox_token or os.environ.get(dropbox_token_envvar or "") or ""

    dbx = dropbox.Dropbox(dropbox_token, session=session)
    upload_to_dropbox(dbx, target_path, src_file)


def __entry_point():
    import argparse

    parser = argparse.ArgumentParser(
        description="",  # プログラムの説明
    )
    parser.add_argument("-s", "--src-file", type=argparse.FileType("rb"))
    parser.add_argument("-d", "--target-path")
    parser.add_argument("-t", "--dropbox-token")
    parser.add_argument("-e", "--dropbox-token-envvar")
    main(**dict(parser.parse_args()._get_kwargs()))


if __name__ == "__main__":
    __entry_point()

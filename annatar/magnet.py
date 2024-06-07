import re
import hashlib


def parse_magnet_link(uri: str) -> str:
    match = re.search("btih:([a-zA-Z0-9]+)", uri)
    if match:
        return match.group(1).upper()
    raise ValueError(f"Invalid magnet link: {uri}")

def make_magnet_link(info_hash: str) -> str:
    return f"magnet:?xt=urn:btih:{info_hash}"

def bdecode(data: bytes) -> dict:
    def decode_next(data: bytes, index: int):
        if data[index] == ord("i"):
            index += 1
            end = data.index(b"e", index)
            number = int(data[index:end])
            return number, end + 1
        elif data[index] == ord("l"):
            index += 1
            lst = []
            while data[index] != ord("e"):
                value, index = decode_next(data, index)
                lst.append(value)
            return lst, index + 1
        elif data[index] == ord("d"):
            index += 1
            dct = {}
            while data[index] != ord("e"):
                key, index = decode_next(data, index)
                value, index = decode_next(data, index)
                dct[key] = value
            return dct, index + 1
        elif data[index] in b"0123456789":
            colon = data.index(b":", index)
            length = int(data[index:colon])
            start = colon + 1
            end = start + length
            string = data[start:end]
            return string, end
        else:
            raise ValueError("Invalid bencode format")
    
    result, _ = decode_next(data, 0)
    return result

def bencode(value) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    elif isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    elif isinstance(value, str):
        return bencode(value.encode())
    elif isinstance(value, list):
        return b"l" + b"".join(bencode(v) for v in value) + b"e"
    elif isinstance(value, dict):
        items = sorted(value.items())
        return b"d" + b"".join(bencode(k) + bencode(v) for k, v in items) + b"e"
    else:
        raise TypeError("Unsupported type for bencoding")
    
async def get_info_hash(response) -> str:
    torrent_data = await response.read()
    torrent_dict = bdecode(torrent_data)
    info = bencode(torrent_dict[b"info"])
    info_hash = hashlib.sha1(info).hexdigest()

    return info_hash
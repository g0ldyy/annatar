import re
import hashlib
import bencodepy


def parse_magnet_link(uri: str) -> str:
    match = re.search("btih:([a-zA-Z0-9]+)", uri)
    if match:
        return match.group(1).upper()
    raise ValueError(f"Invalid magnet link: {uri}")

def make_magnet_link(info_hash: str) -> str:
    return f"magnet:?xt=urn:btih:{info_hash}"
    
async def get_info_hash(response) -> str:
    torrent_data = await response.read()
    torrent_dict = bencodepy.decode(torrent_data)
    info = bencodepy.encode(torrent_dict[b"info"])
    info_hash = hashlib.sha1(info).hexdigest()

    return info_hash
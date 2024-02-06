# Annatar

![](https://i.imgur.com/UIVsFy7.png)

**Annatar** - Lord of Gifts. A [Stremio](https://www.stremio.com/) plugin enabling you to search popular torrent sites and debrid caches for streamable content.

**<u>DISCLAIMER</u>**: *This code does not interact with torrent protocols, nor does it download or stream any content whatsoever. It is a Stremio plugin that provides only metadata and links by searching torrent indexers for content and searching Debrid services.* 

This plugin is implemented in python using tie [Stremio protocol definition](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md).

## Running Locally

1. Install docker and docker-compose
2. Clone this repo
3. `docker-compose up -d`
4. open http://localhost:9117/
5. Add some indexers (**DO NOT CHOOSE SLOW INDEXERS**). I recommend the ones pictured below for almost all TV and Movies. They are the fastest providers. ![](https://i.imgur.com/gYPNEyM.png)
6. Copy your API Key from Jackett (top right)
7. edit `docker-compose.yaml` and paste your API key under `annatar -> env -> JACKETT_API_KEY`
8. `docker-compose restart annatar`

## Torrentio is Better

If you want a button-click torrent indexer and searcher then go with Torrentio. This is a self-hosted alternative for when [Torrentio is down](https://www.reddit.com/r/StremioAddons/comments/1acl7ss/torrentio_faq/) or if you prefer to host your own software.



## How It Works

Torrentio gives you instant results because it indexes content out of band of the search API. Meaning, when you search something against Torrentio you are interacting with a cached dataset. That improves performance but costs more resources and a lot more code. 

The current problem with other alternatives is that they are _very_ slow. 

Because of how it is written, Annatar gives you _fast enough_ results depending on the indexer you are using. My experience with the indexers above have yielded results in Stremio almost always **under 5 seconds and usually around 3 seconds**. Annatar uses asyncio and multi-threadding to divide and conquer. When a search request is received it queries all indexers in parallel. 

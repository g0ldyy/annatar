# Annatar - Lord of Gifts

![](https://i.imgur.com/UIVsFy7.png)

Annatar is free as in beer. If you are feeling generous I accept donations at [Ko-fi](https://ko-fi.com/annatar).

---

The **fastest** just-in-time torrent/debrid search add-on for [Stremio](https://www.stremio.com/) providing results in under 2-3s.

Annatar searches torrent and debrid sites for cached content to provide instantly available content for Stremio. Results from Annatar typically arrive in **3s or less**. Annatar achieves its speed by using several fanout queries and map-reduce functions to gather the fastest and most accurate results using Jackett APIs. 

I created this plugin because I wanted a self-hosted alternative to Torrentio. 

## The Fastest

There are other plugins that are similar to Annatar, but my experience with them has been not great. Results typically take over 10s which is far from ideal. Annatar is fast enough that the short delay does not bother me. Content is cached using [redislite](https://redislite.readthedocs.io/en/latest/). This includes debrid links, Torrent metadata, and Jackett search results. 

Cache is built based on user-requests. Each new imdb id will be cold requested from Jackett, Cinemeta, and Debrid. Subsequent requests will retrieve cache (given some TTLs depending on arbitrary logic).

## FREE Community Edition

Although I wrote Annatar to be self-hosted it is also available as a [Community Edition](https://annatar.elfhosted.com/configure) thanks to sponsorship from https://elfhosted.com. If you want to customize Annatar but you can't self-host you can easily get your own instance with [just a few clicks](https://elfhosted.com/app/annatar/). 

## Running Locally

:warning: **IMPORTANT NOTE ABOUT REAL DEBRID**: If you are using RD you should be aware of their IP restrictions. If you stream from more than one IP at a time you will receive a warning and then a ban. The IP address tied to the stream depends on how you configure Annatar. By default Annatar will not forward the client IP address. This means that in your [RD Downloads](https://real-debrid.com/downloads) page you will see the public IP address of the Annatar server and not the client streaming the content. If you would like to forward the client IP (your phone or TV) then set the environment variable `FORWARD_ORIGIN_IP: "true"`. If you are behind a reverse proxy make sure the proxy is setting x-real-ip or x-forwarded-for headers to the origin IP address. If you want to send a static IP address you can set `OVERRIDE_ORIGIN_IP: "<some IP>"` and that will take precedence. 

---

**Annatar must be accessible by Stremio via HTTPS**. Run it on a desktop, VM, or server somewhere that your Stremio apps can reach it. You will need HTTPS otherwise Stremio will not install the plugin. See #1 for comments. 

Annatar does not import certificates. You will likely need a reverse proxy such as nginx or Caddy. See #1 comments for an nginx example.

 ### If You Already Have Jackett

```
docker run -d -p 8000:8000 -v ./annatar-data:/app/data --name annatar \
	-e JACKETT_URL=<your jackett URL> \
	-e JACKETT_API_KEY=<your jackett api key> \
	-e JACKETT_INDEXERS=eztv,kickasstorrents-ws,thepiratebay,therarbg,torrentgalaxy,yts,badasstorrents,limetorrents,bitsearch \
	registry.gitlab.com/stremio-add-ons/annatar:latest
```

### If you don't already have Jackett

```bash
# create a working directory
mkdir -p annatar
cd annatar
# Download the docker-compose
curl -LJO https://gitlab.com/stremio-add-ons/annatar/-/raw/master/docker-compose.yaml
docker-compose up -d jackett
```

Open http://localhost:9117 and add some indexers. I recommend the ones pictured below for almost all TV and Movies. They are the fastest providers. If someone wants to suggest others open a PR (i.e. anime indexers). 

![](https://i.imgur.com/gYPNEyM.png)

Edit `docker-compose.yaml` and paste your API key under `annatar -> env -> JACKETT_API_KEY`

Run Annatar. `docker-compose up -d`

Install the add-on to Stremio:

1. Open `http://<host>:8000/configure` on a machine that has Stremio installed

2. Type in your details and click Install

   ![](./img/configure.png)

3. This will launch the plugin the Stremio app. 

## This is not Torrentio

Torrentio provides instant results because it uses a crawler to cache content from indexers. All searches against the Torrentio add-on yield results from cached content. While this provides instant results it comes at a cost. Sometimes that [cost is downtime](https://www.reddit.com/r/StremioAddons/comments/1acl7ss/torrentio_faq/), but it also means that Torrentio caches much more than I need or care to know about. Also, because of this added complexity it is [non-trivial](https://github.com/Gabisonfire/knightcrawler) to self-host Torrentio. 



## FAQ

- **Q: Annatar is slow**
  - A: It's possible you are using slow indexers. Open Jackett directly and search individual indexers and see which one returns slowly. Disable that indexer if it is slow or be patient and wait for the cache to build
- **Q: Can you add support for** `<debrid provider>`
  - A: Yes. Vote for an existing issue or create a new one to request it. I'll do what I can
- **Q: What is Annatar**
  - A: Annatar - Lord of Gifts was the guise that Sauron assumed during the Second Age of Middle Earth.
- **Q: Can you add support for download-to-debrid links**
  - A: No. Annatar is exclusively for instantly available content found on supported debrid services.
- **Q: Can you add support for torrent streaming?**
  - A: No. Annatar is exclusively for instantly available content found on supported debrid services.

---

## Contributing/Development

This plugin is implemented in python using the [Stremio protocol definition](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md).

---

**<u>DISCLAIMER</u>**: *This software does not interact with torrent protocols, nor does it download or stream any content whatsoever. It is a Stremio plugin that provides only metadata and links by searching torrent indexers for content and searching Debrid services. Interacting with torrent indexers may be illegal in your country.* 

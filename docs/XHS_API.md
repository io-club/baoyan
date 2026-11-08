# XHS Collector HTTP API

The service wraps the pinned `Spider_XHS` implementation.

Agent entry URL: `http://gateway:8080/api/xhs`
Direct internal URL for platform services: `http://xhs:5000`

## Search notes

```http
POST /notes/search
Content-Type: application/json

{
  "query": "计算机视觉 夏令营",
  "cookie": "<logged-in xiaohongshu cookie>",
  "limit": 10,
  "sort": 0,
  "note_type": 0,
  "time_range": 0
}
```

The endpoint removes duplicate note IDs and returns note details when retrieval
succeeds. A failed detail request is retained with `detail_error` so one bad
note does not discard the rest of the search results.

## Note detail

```http
POST /notes/detail
Content-Type: application/json

{
  "url": "https://www.xiaohongshu.com/explore/...",
  "cookie": "<logged-in xiaohongshu cookie>"
}
```



import os
import json
import sqlite3
import argparse
import requests
import pandas as pd

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("NEWS_API_KEY")
DB_NAME = "news.db"


def fetch_news(keyword="technology", page_size=50):
    if not API_KEY:
        raise ValueError("Set NEWS_API_KEY in your .env file.")

    response = requests.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": keyword,
            "pageSize": page_size,
            "sortBy": "publishedAt",
            "language": "en",
            "apiKey": API_KEY,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "ok":
        raise RuntimeError(data.get("message", "News API error"))

    articles = []

    for item in data.get("articles", []):
        url = item.get("url")
        if not url:
            continue

        articles.append({
            "title": item.get("title"),
            "source": item.get("source", {}).get("name"),
            "author": item.get("author"),
            "description": item.get("description"),
            "url": url,
            "published_at": item.get("publishedAt"),
            "fetched_at": datetime.now().astimezone().isoformat(),
        })

    return articles


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                author TEXT,
                description TEXT,
                published_at TEXT,
                fetched_at TEXT
            )
        """)


def save_articles(articles):
    with sqlite3.connect(DB_NAME) as conn:
        before = conn.total_changes

        conn.executemany("""
            INSERT OR IGNORE INTO articles
            (url, title, source, author, description,
             published_at, fetched_at)
            VALUES
            (:url, :title, :source, :author, :description,
             :published_at, :fetched_at)
        """, articles)

        inserted = conn.total_changes - before

    print(f"Saved {inserted} new articles.")
    print(f"Skipped {len(articles) - inserted} duplicates.")


def get_articles(source=None, keyword=None,
                 start_date=None, end_date=None):
    query = "SELECT * FROM articles WHERE 1=1"
    params = []

    if source:
        query += " AND LOWER(source) LIKE LOWER(?)"
        params.append(f"%{source}%")

    if keyword:
        query += """
            AND (LOWER(title) LIKE LOWER(?)
            OR LOWER(description) LIKE LOWER(?))
        """
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    if start_date:
        query += " AND date(published_at) >= date(?)"
        params.append(start_date)

    if end_date:
        query += " AND date(published_at) <= date(?)"
        params.append(end_date)

    query += " ORDER BY published_at DESC"

    with sqlite3.connect(DB_NAME) as conn:
        return pd.read_sql_query(query, conn, params=params)


def export_articles(df, fmt):
    os.makedirs("exports", exist_ok=True)
    path = f"exports/news.{fmt}"

    if fmt == "json":
        df.to_json(path, orient="records", indent=2)
    elif fmt == "csv":
        df.to_csv(path, index=False)
    elif fmt == "excel":
        df.to_excel(path, index=False)
    else:
        raise ValueError("Choose json, csv, or excel")

    print(f"Exported {len(df)} articles to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="News Aggregator CLI"
    )

    parser.add_argument(
        "action", choices=["fetch", "list", "export"]
    )
    parser.add_argument("--query", default="technology")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source")
    parser.add_argument("--keyword")
    parser.add_argument("--from-date", dest="start_date")
    parser.add_argument("--to-date", dest="end_date")
    parser.add_argument(
        "--format", choices=["json", "csv", "excel"],
        default="csv"
    )

    args = parser.parse_args()
    init_db()

    if args.action == "fetch":
        articles = fetch_news(args.query, args.limit)
        save_articles(articles)

    else:
        df = get_articles(
            source=args.source,
            keyword=args.keyword,
            start_date=args.start_date,
            end_date=args.end_date,
        )

        if args.action == "list":
            print(df.to_string(index=False))
            print(f"\nTotal articles: {len(df)}")
        else:
            export_articles(df, args.format)


if __name__ == "__main__":
    main()

# database.py

import os
import threading
import time
from datetime import datetime
from typing import Dict, List

import schedule
from langchain_chroma import Chroma
from langchain_community.vectorstores import VectorStore
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from scraper import BlogScraper

cfg = {
    "TOPICS": [
        "health",
        "fitness",
        "technology",
        "entertainment",
        "movies",
    ],
}


class BlogDatabase:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.embedding_function = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.persist_directory = persist_directory
        self.vector_store = self._load_or_create_vector_store()
        self.scraper = BlogScraper()
        self.last_update = self._get_last_update()
        self.topics = cfg["TOPICS"]

    def _load_or_create_vector_store(self) -> VectorStore:
        return Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_function,
        )

    def _get_last_update(self) -> datetime:
        if os.path.exists(os.path.join(self.persist_directory, "last_update.txt")):
            with open(
                os.path.join(self.persist_directory, "last_update.txt"), "r"
            ) as f:
                return datetime.fromisoformat(f.read().strip())
        return None

    def _save_last_update(self):
        with open(os.path.join(self.persist_directory, "last_update.txt"), "w") as f:
            f.write(datetime.now().isoformat())

    def add_articles(self, articles: List[Dict[str, str]]):
        documents = [
            Document(
                page_content=article["content"],
                metadata={
                    "source": article["url"],
                    "topic": article["topic"],
                },
            )
            for article in articles
        ]
        self.vector_store.add_documents(documents)
        # self.vector_store.persist() Since Chroma 0.4.x, the vector store is automatically persisted

    def search(
        self, query: str, topic: str, k: int = 7
    ) -> List[Document]:
        filter_dict = {"topic": topic}
        return self.vector_store.similarity_search(query, k=k, filter=filter_dict)

    def update_database(self):
        print("Starting database update...")
        all_new_articles = []
        for topic in self.topics:
            print(f"Scraping blogs for topic: {topic}")
            new_articles = self.scraper.scrape_blogs(
                [topic], urls_per_topic=10
            )[topic]
            for article in new_articles:
                article["topic"] = topic
            all_new_articles.extend(new_articles)
            print(f"  Found {len(new_articles)} new articles for topic: {topic}")

        print(f"Adding {len(all_new_articles)} new articles to the database...")
        self.add_articles(all_new_articles)
        self._save_last_update()
        self.last_update = datetime.now()
        print(f"Database updated at {self.last_update}")

    def start_automatic_updates(self):
        def update_job():
            self.update_database()

        schedule.every(8).hours.do(update_job)

        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(1)

        thread = threading.Thread(target=run_schedule)
        thread.start()


if __name__ == "__main__":
    # Test the database
    db = BlogDatabase()

    # Initial update
    db.update_database()
import requests
import json
import xml.etree.ElementTree as ET

# Notion API の設定（自分の情報に置き換えてください）
NOTION_DATABASE_ID = "c3d0a44b74434efbb95ea7b9cc6c0cee"
NOTION_TOKEN = "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"

# カバー画像を取得する関数（書影API → OpenBD → Google Books）
def fetch_cover_image(isbn):
    cover_image = fetch_ndl_cover(isbn)
    if cover_image:
        return cover_image

    cover_image = fetch_openbd_cover(isbn)
    if cover_image:
        return cover_image

    cover_image = fetch_google_books_cover(isbn)
    if cover_image:
        return cover_image

    return "なし"

# NDL API から書影を取得
def fetch_ndl_cover(isbn):
    ndl_url = f"https://ndlsearch.ndl.go.jp/thumbnail/{isbn}.jpg"
    response = requests.head(ndl_url)
    if response.status_code == 200:
        return ndl_url
    return ""

# OpenBD からカバー画像を取得
def fetch_openbd_cover(isbn):
    url = f"https://api.openbd.jp/v1/get?isbn={isbn}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data and data[0] and "onix" in data[0]:
            for resource in data[0]["onix"].get("CollateralDetail", {}).get("SupportingResource", []):
                if resource.get("ResourceContentType") == "01":
                    for version in resource.get("ResourceVersion", []):
                        if "ResourceLink" in version:
                            return version["ResourceLink"]
    return ""

# Google Books API からカバー画像を取得
def fetch_google_books_cover(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if "items" in data and len(data["items"]) > 0:
            volume_info = data["items"][0].get("volumeInfo", {})
            image_links = volume_info.get("imageLinks", {})
            return image_links.get("thumbnail", "")
    return ""

# OpenBD API で書籍情報を取得
def fetch_book_data(isbn):
    isbn = isbn.replace("-", "")
    url = f"https://api.openbd.jp/v1/get?isbn={isbn}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if data and data[0] is not None and "summary" in data[0]:
            book = data[0]['summary']
            
            description, toc = fetch_openbd_texts(data[0])
            cover_image = fetch_cover_image(isbn)
            
            amazon_link = f"https://www.amazon.co.jp/s?k={isbn}"
            calil_link = f"https://api.calil.jp/openurl?rft.isbn={isbn}"
            
            return {
                "title": book.get("title", "不明"),
                "author": book.get("author", "不明"),
                "publisher": book.get("publisher", "不明"),
                "published_date": book.get("pubdate", "不明"),
                "isbn": isbn,
                "cover_image": cover_image,
                "amazon_link": amazon_link,
                "calil_link": calil_link,
                "description": description,
                "toc": toc
            }
    return None

# OpenBD から内容紹介と目次を取得
def fetch_openbd_texts(book_data):
    description = ""
    toc = ""
    
    if "onix" in book_data and "CollateralDetail" in book_data["onix"]:
        for text_content in book_data["onix"]["CollateralDetail"].get("TextContent", []):
            if text_content.get("TextType", "") == "03":  # 内容紹介
                description = text_content.get("Text", "")
            elif text_content.get("TextType", "") == "04":  # 目次
                toc = text_content.get("Text", "")
    
    return description.strip() or "内容紹介なし", toc.strip() or "目次情報なし"

# Notion API へデータを追加
def add_book_to_notion(book_data):
    notion_url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    children_blocks = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "📖 内容紹介"}}]
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": book_data["description"]}}]
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "📜 目次"}}]
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": book_data["toc"]}}]
            }
        }
    ]

    notion_payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "書名": {"title": [{"text": {"content": book_data["title"]}}]},
            "著者名": {"rich_text": [{"text": {"content": book_data["author"]}}]},
            "出版社": {"rich_text": [{"text": {"content": book_data["publisher"]}}]},
            "出版年月": {"rich_text": [{"text": {"content": book_data["published_date"]}}]},
            "ISBN": {"rich_text": [{"text": {"content": book_data["isbn"]}}]},
            "Amazonリンク": {"url": book_data["amazon_link"]},
            "カーリルリンク": {"url": book_data["calil_link"]},
            "カバー画像": {"files": [{"name": "cover", "external": {"url": book_data["cover_image"]}}]} if book_data["cover_image"] else {"files": []}
        },
        "children": children_blocks
    }

    response = requests.post(notion_url, headers=headers, data=json.dumps(notion_payload))
    
    if response.status_code in [200, 201]:
        return True
    else:
        print("Notion API エラー:", response.text)
        return False

# ISBN を手入力して連続登録
def main():
    print("📚 OpenBD → Notion 書籍登録ツール")
    
    while True:
        isbn = input("ISBN を入力してください（終了する場合は 'exit' を入力）：").strip()
        if isbn.lower() == "exit":
            print("✅ 終了しました。")
            break
        
        book_data = fetch_book_data(isbn)
        if book_data:
            print(f"📖 取得した書籍情報: {book_data['title']} / {book_data['author']}")
            print(f"📜 目次: {book_data['toc'][:100]}...")
            success = add_book_to_notion(book_data)
            if success:
                print(f"✅ 『{book_data['title']}』を Notion に登録しました。\n")
            else:
                print("⚠️ 登録に失敗しました。\n")
        else:
            print("⚠️ ISBN に対応する書籍情報が見つかりませんでした。\n")

if __name__ == "__main__":
    main()

"""One-off helper: list folders with images that have a bird-related keyword (keywords_dim LIKE %birds%)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db  # noqa: E402


def main():
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT FIRST 20 f.path, COUNT(DISTINCT i.id) AS cnt
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        WHERE EXISTS (
            SELECT 1 FROM image_keywords ik
            JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
            WHERE ik.image_id = i.id AND kd.keyword_norm LIKE '%birds%'
        )
        GROUP BY f.path
        ORDER BY cnt DESC
        """
    )
    rows = c.fetchall()
    conn.close()
    for row in rows:
        print(f"{row[1]}\t{row[0]}")
    if not rows:
        print("No folders with bird-keyword images found.", file=sys.stderr)
        sys.exit(1)
    return rows[0][0]


if __name__ == "__main__":
    main()

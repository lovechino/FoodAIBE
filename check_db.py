import sqlite3

conn = sqlite3.connect(r'e:\AI_online\data\ha_noi\food.db')
cur = conn.cursor()

cur.execute("PRAGMA table_info(food)")
cols = cur.fetchall()
print('ALL Columns of food:')
for c in cols:
    print(f"  [{c[0]}] {c[1]} ({c[2]})")

print('\nSample row (full):')
cur.execute('SELECT * FROM food LIMIT 1')
row = cur.fetchone()
cur.execute("PRAGMA table_info(food)")
col_names = [c[1] for c in cur.fetchall()]
for i, val in enumerate(row):
    print(f"  {col_names[i]}: {val}")

conn.close()

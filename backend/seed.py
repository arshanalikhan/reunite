"""Seed the prototype with three simulated Assam flood relief camps.

    python seed.py            # reset and seed

Optional: drop face photos into backend/seed_photos/ named
    Name_Age_Gender_CAMP-X_Tent.jpg     e.g.  Riya Das_6_female_CAMP-B_14.jpg
and they are registered with real face embeddings.
"""
import os
import random

import db
from face_engine import engine
from matching import MIN_SAVE, score

random.seed(7)

CAMPS = [
    ("CAMP-A", "Silchar Relief Camp A", "Cachar", 24.8333, 92.7789, 1200),
    ("CAMP-B", "Dhubri Relief Camp B", "Dhubri", 26.0207, 89.9743, 900),
    ("CAMP-C", "Barpeta Relief Camp C", "Barpeta", 26.3229, 91.0060, 700),
]

# name, age, gender, origin village/district, distinguishing marks, camp, tent
PEOPLE = [
    ("Riya Das", 6, "female", "Gauripur, Dhubri", "red frock, mole on left cheek", "CAMP-B", "14"),
    ("Abdul Karim", 71, "male", "Bilasipara, Dhubri", "white beard, walking stick, hearing aid", "CAMP-B", "3"),
    ("Mousumi Begum", 34, "female", "Golakganj, Dhubri", "green saree, burn scar right hand", "CAMP-B", "9"),
    ("Bikash Roy", 12, "male", "Chapar, Dhubri", "school uniform, broken front tooth", "CAMP-B", "14"),
    ("Hasina Khatun", 67, "female", "Agomani, Dhubri", "cataract left eye", "CAMP-B", "2"),
    ("Pranjal Nath", 45, "male", "Sonai, Cachar", "tattoo on forearm", "CAMP-A", "5"),
    ("Laxmi Sinha", 8, "female", "Lakhipur, Cachar", "pink bangles, two plaits", "CAMP-A", "11"),
    ("Rafiqul Islam", 29, "male", "Katigorah, Cachar", "limps, blue shirt", "CAMP-A", "7"),
    ("Kamala Devi", 78, "female", "Udharbond, Cachar", "white saree, uses spectacles", "CAMP-A", "1"),
    ("Arjun Paul", 4, "male", "Silchar town, Cachar", "yellow t-shirt, birthmark on neck", "CAMP-A", "11"),
    ("Nazma Bibi", 52, "female", "Borkhola, Cachar", "diabetic, carries insulin", "CAMP-A", "4"),
    ("Debojit Kalita", 38, "male", "Sarthebari, Barpeta", "moustache, scar on chin", "CAMP-C", "6"),
    ("Pinky Barman", 15, "female", "Howly, Barpeta", "glasses, red school bag", "CAMP-C", "8"),
    ("Jahanara Ahmed", 61, "female", "Sorbhog, Barpeta", "gold nose pin", "CAMP-C", "2"),
    ("Manik Deka", 9, "male", "Barpeta Road", "missing shoe, cut on knee", "CAMP-C", "8"),
    ("Suren Medhi", 83, "male", "Pathsala, Barpeta", "dementia, does not remember name", "CAMP-C", "1"),
    ("Anowara Begum", 27, "female", "Kalgachia, Barpeta", "pregnant, purple scarf", "CAMP-C", "5"),
    (None, 3, "male", "unknown", "found alone near Beki river, orange shorts", "CAMP-C", "8"),
    (None, 70, "female", "unknown", "speaks Bodo, cannot recall village, red shawl", "CAMP-A", "1"),
    ("Tarun Gogoi", 19, "male", "Mankachar, South Salmara", "football jersey no. 10", "CAMP-B", "6"),
    ("Sahida Parvin", 11, "female", "Fakirganj, Dhubri", "hearing impaired, wears hijab", "CAMP-B", "14"),
    ("Hemanta Bora", 56, "male", "Jalah, Barpeta", "grey kurta", "CAMP-C", "6"),
    ("Mina Rabha", 42, "female", "Dudhnoi, Goalpara", "Rabha earrings", "CAMP-B", "9"),
    ("Imran Hussain", 7, "male", "Hatsingimari, South Salmara", "green cap", "CAMP-B", "14"),
]

# Families who already searched (no photos) - creates pending candidates to review.
REPORTS = [
    dict(seeker_name="Abdul Rahim", seeker_phone="98xxxxxx21", relation="Son", name="Abdul Karim", age=72,
         gender="male", last_seen="Bilasipara market", marks="walking stick, white beard"),
    dict(seeker_name="Gita Paul", seeker_phone="94xxxxxx07", relation="Mother", name="Arjun", age=4,
         gender="male", last_seen="Silchar", marks="yellow t-shirt"),
    dict(seeker_name="Ramesh Deka", seeker_phone="70xxxxxx55", relation="Father", name="Manik", age=9,
         gender="male", last_seen="Barpeta Road station", marks="cut on knee"),
]


def ref(prefix):
    return f"{prefix}-{random.randrange(16**6):06X}"


def main():
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.init()
    with db.connect() as con:
        for c in CAMPS:
            con.execute("INSERT INTO camps(code,name,district,lat,lng,capacity) VALUES (?,?,?,?,?,?)", c)
        camp_id = {r["code"]: r["id"] for r in con.execute("SELECT id, code FROM camps")}

        rows = list(PEOPLE)
        photo_dir = os.path.join(os.path.dirname(__file__), "seed_photos")
        photos = {}
        if os.path.isdir(photo_dir):
            for fn in sorted(os.listdir(photo_dir)):
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                parts = stem.split("_")
                if len(parts) < 4:
                    continue
                name, age, gender, camp = parts[:4]
                tent = parts[4] if len(parts) > 4 else ""
                rows.append((name, int(age), gender, "", "", camp, tent))
                photos[len(rows) - 1] = os.path.join(photo_dir, fn)

        for i, (name, age, gender, origin, marks, camp, tent) in enumerate(rows):
            photo, emb = None, None
            if i in photos:
                data = open(photos[i], "rb").read()
                vec = engine.embed(data)
                emb = vec.tobytes() if vec is not None else None
                photo = f"seed_{i}{os.path.splitext(photos[i])[1].lower()}"
                with open(os.path.join(db.PHOTO_DIR, photo), "wb") as fh:
                    fh.write(data)
                print(f"  photo {os.path.basename(photos[i])}: face {'found' if emb else 'NOT found'}")
            con.execute(
                """INSERT INTO people(ref,name,age,gender,origin,marks,camp_id,tent,photo,embedding,consent,
                                      created_at) VALUES (?,?,?,?,?,?,?,?,?,?,1,
                                      datetime('now', ?))""",
                (ref("REG"), name, age, gender, origin, marks, camp_id[camp], tent, photo, emb,
                 f"-{random.randint(30, 4000)} minutes"))
            con.execute("INSERT INTO alerts(kind,message,camp_id) VALUES ('intake',?,?)",
                        (f"{name or 'Unidentified person'} registered", camp_id[camp]))

        people = con.execute("""SELECT p.*, c.name AS camp_name FROM people p
                                JOIN camps c ON c.id=p.camp_id""").fetchall()
        for r in REPORTS:
            rr = ref("RPT")
            con.execute("""INSERT INTO reports(ref,seeker_name,seeker_phone,relation,name,age,gender,last_seen,marks)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (rr, r["seeker_name"], r["seeker_phone"], r["relation"], r["name"], r["age"],
                         r["gender"], r["last_seen"], r["marks"]))
            rep = con.execute("SELECT * FROM reports WHERE ref=?", (rr,)).fetchone()
            for p in people:
                s = score(rep, p)
                if s and s["confidence"] >= MIN_SAVE:
                    con.execute("""INSERT INTO matches(report_id,person_id,confidence,face_score,text_score,method)
                                   VALUES (?,?,?,?,?,?)""",
                                (rep["id"], p["id"], s["confidence"], s["face_score"], s["text_score"], s["method"]))
                    con.execute("INSERT INTO alerts(kind,message,camp_id) VALUES ('match',?,?)",
                                (f"Text match {s['confidence']:.0f}% for report {rr}: {p['ref']} at {p['camp_name']}",
                                 p["camp_id"]))
    print(f"Seeded {len(CAMPS)} camps, {len(rows)} people, {len(REPORTS)} family reports. "
          f"Face engine: {engine.backend}")


if __name__ == "__main__":
    main()

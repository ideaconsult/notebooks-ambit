# + tags=["parameters"]
upstream = None
folder_output = None
# -


import spacy
#spacy.prefer_gpu()
nlp = spacy.load("en_core_web_sm")

text = ("Maximum Feret diameter: The maximum distance between the two parallel tangents touching the particle outline in all directions.")
doc = nlp(text)

# Analyze syntax
print("Noun phrases:", [chunk.text for chunk in doc.noun_chunks])
print("Verbs:", [token.lemma_ for token in doc if token.pos_ == "VERB"])

# Find named entities, phrases and concepts
for entity in doc.ents:
    print(entity.text, entity.label_)


doc = nlp("Apple is looking at buying U.K. startup for $1 billion")
for token in doc:
    print(token.text, token.lemma_, token.pos_, token.tag_, token.dep_,
            token.shape_, token.is_alpha, token.is_stop)
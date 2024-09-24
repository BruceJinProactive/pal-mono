import spacy

nlp = spacy.load("en_core_web_lg")

doc1 = nlp("Pesto")
doc2 = nlp("pesto")

print(doc1.similarity(doc2))

doc1 = nlp("Cowell's Combo")
doc2 = nlp("cowells combo")
doc3 = nlp("cowellscombo")

print(doc1.similarity(doc2), doc1.similarity(doc3))


def remove_non_alnum_chars(text):
    return "".join([char.lower() for char in text if char.isalnum() or char.isspace()])


doc1_text = remove_non_alnum_chars("Cowell's Combo")
doc2_text = remove_non_alnum_chars("cowells combo")
doc3_text = remove_non_alnum_chars("cowellscombo")
doc1 = nlp(doc1_text)
doc2 = nlp(doc2_text)
doc3 = nlp(doc3_text)

print(doc1_text, doc2_text, doc3_text)
print(doc1.similarity(doc2), doc1.similarity(doc3))

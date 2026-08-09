"""Deterministic issue vocabulary, derived from the stances people actually wrote.

The site's topic chips are terms candidates actually used — nothing invented,
nothing censored. This module:

  1. extracts candidate keyphrases from the stance texts (yake),
  2. strips only structural junk (stopwords, punctuation fragments,
     verb-end n-gram artifacts) — never editorial choices,
  3. canonicalizes near-duplicates to the most frequent variant,
  4. assigns each candidate the vocabulary terms present in their stances.

Every label in the vocabulary is a phrase that appears in the spreadsheet.
"""

import re

import yake

# Stopword-ish tokens that carry no meaning on their own.
NOISE_TOKENS = {
    "a", "an", "the", "and", "or", "for", "not", "to", "of", "in", "on", "at",
    "our", "we", "you", "it", "is", "are", "be", "as", "by", "with", "from",
    "n't", "every", "main", "top", "fully", "public",
}

# yake fragments that end in a verb are broken n-grams ("expanding
# healthcare" from "expanding healthcare access"), not spreadsheet terms.
PHRASE_END_VERBS = {
    "expanding", "improving", "improve", "declaring", "funding", "protecting",
    "banning", "enforcing", "connecting", "repealing", "repeal", "raising",
    "building", "lowering", "cutting", "ending", "stopping", "supporting",
    "reforming", "getting", "keeping", "holding", "fighting", "fixing",
    "saving", "starting", "working", "bringing", "taking", "removing",
    "ensuring", "providing", "helping", "making", "investing",
    "strengthening", "increasing", "overturning", "overturn", "expand",
    "increase", "strengthen", "protect", "ensure", "provide", "invest",
    "pay", "enforce", "declare", "ban", "cap", "cut", "raise", "lower",
    "fix", "stop", "end", "start", "keep", "hold", "fight", "build", "work",
    "bring", "take", "remove", "help", "make", "get", "support", "fund",
    "reform", "connect", "save", "approving", "declaring",
}

# Verb-led phrases that ARE meaningful chips (their noun is the issue).
ALLOWED_VERB_LED = {"abolish ice", "impeach trump", "free palestine"}

TERM_PATTERN = re.compile(r"^[a-z0-9][a-z0-9'&.,\- ]*[a-z0-9]$")


def extract_vocabulary(stance_texts, top=40):
    """Return a cleaned, frequency-ordered list of canonical issue terms.

    Only multi-word phrases become chips: they are the faithful units of
    meaning people wrote ("abolish ice", "universal healthcare"). Bare
    single tokens ("protect", "end", "fund") are not issues.
    """
    corpus = " ".join(stance_texts)
    extractor = yake.KeywordExtractor(
        lan="en", n=2, top=300, dedupLim=0.7, dedupFunc="seqm",
        windowsSize=2, max_ngram_size=2,
    )
    raw_terms = [term for term, _ in extractor.extract_keywords(corpus)]

    cleaned = [normalize_term(t) for t in raw_terms]
    cleaned = [t for t in cleaned if t and " " in t]
    counts = count_terms(cleaned, stance_texts)
    deduped = canonicalize(cleaned, counts)

    return sorted(deduped, key=lambda t: -counts.get(t, 0))[:top]


def normalize_term(term):
    """Lowercase, strip stopwords and structural junk."""
    lowered = term.lower().strip()
    if not TERM_PATTERN.match(lowered):
        return ""
    tokens = [t for t in lowered.split() if t not in NOISE_TOKENS]
    if not tokens:
        return ""
    if len(tokens) > 1 and tokens[-1] in PHRASE_END_VERBS:
        return ""
    joined = " ".join(tokens)
    if len(tokens) > 1 and tokens[0] in PHRASE_END_VERBS and joined not in ALLOWED_VERB_LED:
        return ""
    if not TERM_PATTERN.match(joined):
        return ""
    return joined


def count_terms(terms, stance_texts):
    """How many candidates' stance texts contain each term."""
    texts = [t.lower() for t in stance_texts]
    counts = {}
    for term in terms:
        counts[term] = sum(1 for text in texts if term in text)
    return counts


def canonicalize(terms, counts):
    """Dedupe near-duplicates, keeping the most frequent variant."""
    order = []
    for term in sorted(terms, key=lambda t: (-counts.get(t, 0), len(t))):
        if any(term in accepted for accepted in order):
            continue
        if any(overlaps(term, accepted) for accepted in order):
            continue
        order.append(term)
    return order


def overlaps(a, b):
    """True when two multi-word phrases share most of their tokens.
    Single tokens never absorb phrases ("ice" does not absorb "abolish ice")."""
    tokens_a = a.split()
    tokens_b = b.split()
    if len(tokens_a) < 2 or len(tokens_b) < 2:
        return False
    shared = len(set(tokens_a) & set(tokens_b))
    return shared / min(len(tokens_a), len(tokens_b)) >= 0.5


def assign_topics(records, vocabulary):
    """Set record['topics'] from the vocabulary terms present in stances.

    A phrase tag applies when the phrase appears verbatim OR when its core
    token (the last noun, singularized) appears — so "healthcare" in the
    stances earns the "universal healthcare" tag, since that phrase is what
    the spreadsheet actually says. The core token is derived from the phrase
    itself; nothing is invented.
    """
    cores = {phrase: singular(core_token(phrase)) for phrase in vocabulary}
    for record in records:
        text = record["stances"].lower()
        tags = []
        for phrase in vocabulary:
            if phrase in text or singular(core_token(phrase)) in text:
                tags.append(phrase)
        record["topics"] = tags


def core_token(phrase):
    """The last word of the phrase, e.g. 'healthcare' in 'universal healthcare'."""
    return phrase.split()[-1]


def singular(token):
    """Naive English singularization, good enough for matching purposes."""
    if len(token) <= 3 or token.endswith("ss") or token.endswith("us"):
        return token
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("es") and token.endswith(("ses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token

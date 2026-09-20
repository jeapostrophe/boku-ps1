# Rulings needed from Jay (PLAN `TRN-01`, `[MINE: product]`)

The charter (README § "Who this is for") settles the kind of translation. These are the
questions it does **not** settle and that genuinely change the script. They are listed **in
order of impact**; the ids are stable labels used by [style-guide.md](style-guide.md),
[glossary.md](glossary.md) and [samples/](samples/), so they are not in numerical order.
Each has the options with the same line rendered under each, a recommendation, and what
depends on the answer. The fastest way to decide most of them is to read the three samples.

Counts are occurrences in the decoded dump of this disc.

---

## Q1 — How are people addressed? (kin terms and name suffixes)

More than 430 lines: *Boku-kun* 171, *Oba-chan* 76, *Onee-chan / Moe-neechan* 73, *Oji-san* 49,
*Oji-chan* 34, *Onii-chan* 16, *Boku-chan* 12, plus *-san / -chan* on other names. The player
hears every one of them.

| option | `E0406.6`–`.7`, `E2805.9` |
|---|---|
| **A. All English** | "Okay, Uncle." / "Thanks, Auntie!" / "Your big brother is your big brother, and Boku is Boku." |
| **B. All as heard** | "Okay, Oji-chan." / "Oba-chan, gochisosama!" / "Onii-chan is Onii-chan. Boku-kun is Boku-kun." |
| **C. Hybrid (recommended)** | "Okay, Uncle." / "Auntie, gochisosama!" / "Onii-chan is Onii-chan. Boku-kun is Boku-kun." |

**Recommendation: C.** Apply the charter's own test for "Boku" — keep the Japanese where
English has no natural word for the job. "Uncle" and "Auntie" *are* what an English-speaking
child calls them, and adults calling themselves "Uncle" / "Auntie" to a small boy is natural
English, so the Japanese habit of self-reference by role survives intact. *-kun / -chan / -san*
and *Onee-chan / Onii-chan used as names* have no English counterpart, carry characterisation
(who says *-kun*, who says *-chan*), and one of them carries the plot: the dead son has no name
but "Onii-chan", and on day 29 Moe greets Boku with that word. Under A that thread becomes
"big brother" and still works, but *Boku-kun* → "Boku" 171 times flattens every relationship
in the house; under B the script is consistent and fully "as heard" but asks the reader to
learn *oji-san / oji-chan / oba-chan* for words English simply has.

**Depends on it:** every scene; speaker labels (Uncle / Aunt either way); the glossary's
people table; Q4.

## Q2 — *Itadakimasu* and *gochisōsama*

124 lines; four choruses a day; the first thing the player hears at every meal.

* **Keep (recommended):** "Itadakimasu!" / "Gochisosama deshita." Day 1: Boku, a beat behind
  everyone, "*...kimasu*" / "*...deshita*" (`E0103.2`, `E0104.2`).
* **Translate:** "Let's eat!" / "Thank you for the meal." Day 1: "*...eat*" / "*...the meal*".

**Why keep:** there is no English act to translate it into; the day-1 joke is about the sound
of the words; and it is the Japanese-ism this audience would most expect to be left alone.
Every other greeting *is* translated (good morning, good night, nice to meet you), so this is
two phrases, not a policy of leaving greetings in Japanese.

**Depends on it:** 65 meal events; the shared lines `E0006`–`E0010`.

## Q3 — Jokes that live in the Japanese language

About twenty-five (bible § 6). Mispronounced grown-up words and loanword mix-ups translate
without help and are not in question. The question is the **homophone** jokes — e.g.
`E2205.3`–`.5`, where Shirabe announces a present of a *chō*-necktie, Boku hears "a trillion",
and Moe corrects them: butterfly → bow tie.

| option | the three lines |
|---|---|
| **a. Literal, with the Japanese word showing (recommended)** | "...and for Dad, a *chō*-necktie!" / "A trillion neckties?" / "*Chō* as in butterfly. A bow tie." |
| b. A new English joke | "...and for Dad, a beau tie!" / "A boyfriend tie?" / "A BOW tie." |
| c. Straight, joke lost | "...and for Dad, a super necktie!" / "A trillion neckties?" / "A bow tie, silly." |

**Recommendation: a.** It is the only option that is both a translation and still a joke; the
player can hear *chō* three times and now knows why. (b) is localisation by definition. (c) is
what machine translation gives, and leaves lines that make no sense. The cost of (a) is an
occasional romanised word in dialogue with its meaning given by the next line.

**Depends on it:** ~25 exchanges; several insect-book entries; the tone of Shirabe and Boku.

## Q11 — Speech that has no text on the disc

The adult narrator's **opening monologue**, the **five epilogues** (which are the payoff of the
whole game), the whale and sunflower **dreams**, radio calisthenics, the television programmes
including the August 15 broadcast, and the monk's sutra are FMV audio or voice-only clips:
there is no text layer to translate (108 voice-only nodes; every STR). README § "What gets
translated" rules FMV text out of scope and says nothing about FMV *speech*.

* **a. Out of scope.** The player gets no English for the ending.
* **b. Translate them now into tracked files** (`translation/fmv/…`, keyed by movie number and
  time), and decide how they reach the screen when the renderer work is further along —
  burned-in subtitles on re-encoded STR frames, an overlay, or at worst a booklet shipped with
  the patch. **(recommended)**
* **c.** Commit to on-screen FMV subtitles as a release requirement.

**Why b:** the text is short, it is the frame of the whole work, and a translation whose reader
cannot understand the last two minutes has not done what the charter promises. Transcribing
needs a listener (or an ASR pass checked by one), so it should start early. Whether (c) is
affordable is an engineering finding, not a style ruling.

**Depends on it:** a new PLAN row if (b) or (c) — *this unit did not file one*; the narrator's
voice (Q8) should be settled with the epilogues in view.

## Q6 — Insect names (57 names, 60 book entries, the boys' dialogue)

The brief's test — keep what a Japanese child says only where English has no natural word —
gives different answers by class:

| class | recommended | example | alternative |
|---|---|---|---|
| class words | English | beetle, stag beetle, cicada, dragonfly, firefly | — |
| butterflies (23) | English common name | Cabbage White, Great Purple Emperor | Monshirochō |
| beetles (8 + 4 ♀) | English, keeping Japanese proper elements | Rhinoceros Beetle, Giant Stag Beetle, Miyama Stag Beetle, Oni Stag Beetle | Kabutomushi, Ō-kuwagata |
| dragonflies (9) | English, literal where that is also the sense of the entry | Ancient Dragonfly, Butterfly Dragonfly; Oniyanma kept | Mukashi-tombo |
| cicadas (6) and singing insects (8) | **Japanese name** | Higurashi, Min-min-zemi, Suzumushi | Evening Cicada, Bell Cricket |

**Why:** the cicadas and crickets are named for their calls, the book spells the calls out, and
the game plays them; and English "common names" for them are field-guide coinages nobody says.
Where a book entry jokes about the Japanese name (14 entries, marked ✎ in the glossary), its
name line carries both: "Chinese Peacock (Karasu-ageha, 'crow swallowtail')".
The all-Japanese alternative is simpler and fully "as heard", but turns the collection screens
into a vocabulary test; the all-English one breaks those fourteen entries.

**Depends on it:** `exe@8003D2E0`, `hhon@5328`, bug-sumo dialogue; the redrawn insect-book
textures.

## Q5 — Place names

* **Recommended:** settlements stay (Tsukiyono, Sagi-no-sato, Okuzawa); descriptive landmarks
  are translated (Firefly Creek, the Cape of Winds, Dragon God Pond, the Great Oak); two
  hybrids because dialogue explains or plays on the name: **the Yukino River** (Shirabe explains
  *yuki*) and **Mt. Teppen** (the narrator: "at the very top of Mt. Teppen").
* **Alternative:** all as heard — Hotaru-zawa, Kaze no Misaki, Ryujin-ike, Teppen-yama.

**Why:** these names were coined to be understood; a player with Google Translate open would
be shown "Firefly Creek". The ear/eye mismatch is real but small (28 occurrences).

**Depends on it:** glossary § 2; the map texture.

## Q4 — The boys' names and the nicknames

* **Recommended:** Guts, Fat, Megane as heard (two are English already; "Megane" is glossed by
  his glasses and by every review of the game); **translate the descriptive nicknames**,
  because they are meant to sting or tease and must be understood at once: *chibi-musume* →
  "Pipsqueak", *ōkami-musume* → "Wolf Girl", *ofuro no onē-san* → "the Bath Lady",
  *moyashikko* → "beansprout". Ken-bō and Nora stay; Jumbo-san stays.
* **Alternative:** "Specs" for Megane; *Chibi-musume* as heard.

**Depends on it:** 163 labelled lines and the nickname uses; Q1 (whether "Gacchan" and "Boku-chan" keep their suffix).

## Q7 — Speaker labels and quotation marks

The Japanese draws `label「…」` inline. Recommended: the label is a **field** in the
translation files, drawn by the renderer; labelled dialogue has **no quotation marks**;
narration is unlabelled and distinguished by the renderer (colour or a rule) rather than by
brackets; system messages are plain. Alternative: `Uncle: "…"` with quotes throughout, which
costs two cells a message and looks like prose rather than a script. This one should be decided
together with whoever does the dialogue band (PLAN § *Text renderer*), since the label may end
up outside the text box altogether.

## Q9 — Macrons

Recommended: **none in game text** ("Yusaku", "Ryujin", "gochisosama"), macrons in documents.
The font has no macron letters; adding ā ī ū ē ō (both cases) is ten glyphs and is the
alternative. "ou / oo / uu" spellings are not recommended under either.

## Q8 — The narrator's voice

Recommended: composed, slightly literary, past tense, no contractions — a memoir read aloud
(sample: `E2805.12`). Alternative: a warmer, colloquial "Wonder Years" voice-over with
contractions. The Japanese is the former: *watashi*, written forms, *oji / oba*. Best decided
with the epilogues in hand (Q11).

## Q10 — Small defaults (accept en bloc, or strike any)

1. *Natsuyasumi* → "summer vacation" in dialogue (Rogers argues for "summer break"; the game's
   own English subtitle is "Summer Holiday 20th Century"). The title stays *Boku no Natsuyasumi*.
2. The 1942 letter's date → "Spring, Showa 17", no gloss. Alt. "Spring 1942".
3. `E1720.4` *okama* → "...A drag queen?" Alt. leave the Japanese word.
4. *Fufu* → "Hm-hm"; other laughs spelled as heard (Gahaha, Kyahaha, Nihihi). Alt. "Fufu".
5. The monk's katakana English → visibly accented English ("How-oldo... are-you?"), then his own
   translation as in the source.
6. A Japanese gloss on an English word (`E0650.11`) is dropped, with a note in the file — the
   only deletion the guide permits.
7. *Mizore* syrup stays "Mizore". Alt. "Plain".
8. *Satoyama* → "the village hills" / "the hills". Alt. keep *satoyama*.
9. Sumo technique names stay Japanese in the bug-sumo move list, as in English sumo
   commentary; the joke moves are translated.
10. The picture diary reads as a correctly-spelled third-grader: short declaratives, no
    deliberate misspellings, hand-lettered.
11. Fish: Iwana, Rainbow Trout, Yamame. Alt. Char / Rainbow Trout / Masu Trout.

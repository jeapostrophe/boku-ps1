# Style guide (PLAN `TRN-01`)

**Status: in force, 2026-09-20.** Everything marked SETTLED BY CHARTER follows from README
§ "Who this is for, and what kind of translation it is". Everything marked **SETTLED (Qn)** was
ruled by Jay on 2026-09-20; the question as put, the options and his words are recorded in
[QUESTIONS.md](QUESTIONS.md), which is a record, not policy — this file is the policy, and a
change to it is made here with a dated note. One ruling (Q7, § 9) is an early default that Jay
marked revisitable; nothing else is open. The story, the cast and how each person talks are
in [bible.md](bible.md); every term that must be rendered one way is in
[glossary.md](glossary.md); the speech that has no text on the disc is listed in
[voice-only.md](voice-only.md). Licence: CC BY-SA 4.0 (`LICENSE-translation`).

Line ids (`E0406.2`, `hhon@5328.13`) are the ones defined in `research/text-format.md` and
`research/text-outside-events.md`. The Japanese for an id exists only in a local import;
short quotations here are examples.

## 0. What the charter already decides

The reader is someone who wants *this* game, overtly Japanese as it is, and needs the words. They
**hear every voiced line in Japanese** while they read. Four consequences run through
everything below:

1. **Translate what is said; do not replace it with what an American family would have said.**
   No substituted foods, shows, jokes, school systems or manners. SETTLED BY CHARTER.
2. **Nothing is cut, softened or modernised.** A nine-year-old in 1975 says things about girls,
   and adults say things about boys, that a 2026 script would not. They are translated at the
   strength they have in the Japanese. SETTLED BY CHARTER (§ 12).
3. **What the ear can check, the eye should not contradict.** A name or a set phrase the player
   hears forty times should not be spelled as something else on screen without a reason. This
   is the argument behind most "keep it" rules below. The charter says Japanese-isms stay; it
   does not say which — those are the rulings marked SETTLED (Qn).
4. **The test for keeping a Japanese word** is the one the charter applies to "Boku": keep it
   when English has no natural word that does the same job; translate it when English does.
   "Uncle" is a natural English form of address; "big brother" used as a name is not.

## 1. Boku

* **His name is Boku.** SETTLED BY CHARTER. The script agrees: he introduces himself with it
  (`E0171.3`), tells Guts "I'm called Boku" (`E0551.7`), and his surname is Kubota
  (`E2904.1`). He has no other given name anywhere in the text.
* **When Boku says *boku* he is saying "I".** He is never made to speak of himself in the third
  person. SETTLED BY CHARTER (the README concedes English cannot keep the ambiguity).
* **The one scene that plays on the ambiguity** is his meeting with Saori (`E1861.3`–`.5`): he
  answers "who are you?" with a sentence that is both "I'm Boku" and "I'm me"; she takes the
  second meaning and dubs him "Boku-kun"; he protests that she has it right. Translate it as
  the name and let her misunderstanding be visible in her line; do not invent a different joke.
  The same construction returns at `E1861.27`.
* Adults address him with the word as a second-person pronoun-name, *Boku-kun*; see § 2.
* **The title phrase occurs in dialogue twice**, in the hiragana of the logo (`E1420.0`,
  `E2320.0`): the aunt tells him Boku's summer vacation is half over, then a week from over.
  Render it "Boku's summer vacation" in the sentence; the game's title itself stays
  *Boku no Natsuyasumi* wherever it appears as a title. SETTLED (Q10.1, 2026-09-20): "summer
  vacation", not "summer break".

## 2. Forms of address — SETTLED (Q1, 2026-09-20)

The script's forms of address, by count in the decoded dump: *Boku-kun* 171, *Oba-chan* 76,
*Onee-chan* / *Moe-neechan* 73, *Oji-san* 49, *Oji-chan* 34, *anta* 50, *Onii-chan* 16,
*Boku-chan* 12.

**The rule is the hybrid** — Jay: *"It is good say 'Uncle/Auntie', but also very good to
include a few -kun."* Kin terms that English has go into English; suffixes and kin terms used
as names stay as heard:

| Japanese | English | why |
|---|---|---|
| name + *-kun*, *-chan*, *-san* | kept as heard: Boku-kun, Boku-chan, Shirabe-chan, Moe-san, Yusaku-san, Gacchan | who uses which suffix is characterisation (the family and Specs say *-kun*; Guts and the monk say *-chan*; Fat says *Moe-san* with a sigh) and the player hears it |
| *oji-chan*, *oji-san* | **Uncle** | a natural English form of address and of self-reference to a child |
| *oba-chan* | **Auntie** | likewise; "Aunt" as the speaker label |
| *otō-san*, *okā-san*, *kā-chan* | Dad, Mom, (your) mom | likewise |
| *onee-chan*, *X-neechan*, *onii-chan* **used as a name** | **kept**: Onee-chan, Moe-neechan, Onii-chan | English has no such name. The parents call Moe "Onee-chan" (`E0402.10`), the dead son has no name but "Onii-chan", and on day 29 Moe congratulates Boku with the same word (`E2907.2`). That thread only exists if the word does |
| the same words used **descriptively** ("the older sister of the house", "become a big brother") | translated: older sister, big brother | they are common nouns there |
| *anta*, *omae*, *kimi* | "you" — the rudeness or bookishness goes into the sentence | |
| Saori's *kā-san* for the aunt | Kaa-san | she is not her mother; "Mom" would mislead. Glossary |

The rejected alternatives — every kin term in English, or every one as heard — are set out
with the same lines rendered each way in Q1 ([QUESTIONS.md](QUESTIONS.md)); the sample that
showed them in full was deleted once day 4 held its lines, and survives in the history as
`translation/samples/family-E0404-E0406.txt` at commit `6a21426`.

**Self-reference by role stays.** Adults talking to Boku call themselves "Uncle" and "Auntie"
("Auntie does the washing first thing every morning", `E0121.0`), Moe calls herself
"Onee-chan", Shirabe calls herself "Shirabe" more often than "I". English does this with small
children, so it carries. Where it would be opaque, use "I". The uncle switches to a plain
adult "I" when he speaks to his wife or muses alone (`E1904.9`, `E2712.0`) — keep that contrast.
SETTLED BY CHARTER as a Japanese-ism that English can hold.

**Name order and romanisation of names** — § 3.

## 3. Romanisation — SETTLED (Q9, 2026-09-20)

* **System:** modified Hepburn. *Shirabe*, *Tsukiyono*, *Sagi-no-sato*; syllabic n as *n*
  (*kanpai*, not *kampai*); particle *no* hyphenated inside place names.
* **Long vowels in game text: unmarked, and no macron glyphs are added to the font.** *Yusaku*,
  *Ryujin*, *Ken-bo*, *gochisosama*. Jay: *"I don't think we need it if it isn't in the
  text."* The game's font sheet has plain A–Z / a–z (`research/font.md`), no macron letters,
  and "ou"/"oo" spellings misread in English (*Yuusaku*, *Oo-kuwagata*). Macrons **are** used
  in this directory's documents, where they cost nothing: Yūsaku, Ryūjin, gochisōsama.
* **Name order:** the script never gives a full name in one breath (the uncle names the house,
  then himself, in two clauses, `E0175.0`), so the question barely arises in game text. In
  documents: family name first with the Japanese, given name first in running English —
  "Yūsaku Sorano (空野優作)". This was not one of the eleven questions; it is the default and
  Jay may reopen it.
* Hyphens: suffixes (*Boku-kun*), place-name particles (*Sagi-no-sato*), compound animal names
  kept in Japanese (*min-min-zemi*). No apostrophes.

## 4. Set phrases and greetings — SETTLED (Q2, 2026-09-20)

**Keep the two mealtime phrases, translate the rest.** Jay: *"Keep them, they are cute
Japanese-isms."*

* *Itadakimasu* and *gochisōsama (deshita)* are said in chorus at every meal — 124 occurrences in
  the dump, heard four times a day. English has no equivalent act, "Let's eat" /
  "Thanks for the meal" are the textbook examples of translating a custom into a different
  custom, and **day 1 turns on the sound of the words**: the new boy can only trail the ends of
  them after everyone else — "*...kimasu*", "*...deshita*" (`E0103.2`, `E0104.2`). Keep:
  "Itadakimasu!", "Gochisosama deshita."
* Greetings with an English equivalent are translated: good morning, hello, good night, thank
  you, excuse me, nice to meet you (*yoroshiku*), welcome. *Osomatsusama* → "It was nothing
  fancy." *Otsukaresama / gokurōsama* → "Thank you for your hard work" / "Good work" by context.
* Shirabe's mock-formal self-introduction (`E0140.8`–`.9`, archaic *-masuru*) → translated, in
  mock-courtly English; Boku copies her wording exactly, so the two lines must match.

## 5. Registers — how people sound

Full portraits are in the bible. The rules:

* **There is no regional dialect in this script.** The Soranos moved from Tokyo; the aunt grew
  up in Otaru and speaks standard Japanese; the local boys speak rough *standard* boys'
  Japanese, not a dialect. One dialect *word* is discussed as such (`E2452.0`, the local name
  for *menko* cards) and is kept and glossed by the line itself. So: **no invented rural English,
  no dropped g's, no "y'all".** SETTLED BY CHARTER (it would be a localisation of something
  that is not there).
* Differences that Japanese carries in pronouns and sentence endings go into **diction and
  rhythm**, never into eye-dialect: Fat's *ore-sama* → "yours truly" and general swagger;
  Guts curt and bossy; Specs bookish, complete sentences, "you know"; Saori blunt, masculine
  endings → short declaratives, "kid", "brat"; polite with the adults. The aunt's feminine
  endings → warmth, "now", "you know"; not "my dear". The uncle's mock-official *desu/masu*
  when laying down rules → mock-official English ("No entry beyond this point at this hour").
* **Children talk like children, not like cartoon children.** Boku is polite, literal and a
  little deadpan. No baby-talk spellings. His mispronunciations of adult words are translated
  as mispronunciations (§ 8).
* **Shirabe** speaks an eight-year-old's idea of a grown lady (*-wa*, *-no yo*, *kashira*,
  "a lady", `E0241.2`): give her prim, over-grown-up English ("How perfectly dreadful",
  "honestly", "one must") and keep her third-person "Shirabe". Her coinages stay as sounds
  (§ 7).
* **Verbal tics are glossary entries**, rendered identically every time: Boku's quiz-show
  deadpan *naze deshō? / nan deshō?* (8 uses, and Moe throws it back at him, `E1632.13`–`.14`);
  the hiccup when he is frightened (*hikku!*, 8); Shirabe's *bayoyōn!* ("Bye-yoyooon!"); the house-rule frame.

## 6. The narrator — SETTLED (Q8, 2026-09-20)

Fifty-one narration messages, bracketed 『 』 in the Japanese, voiced by the adult Boku,
speaker slot 255, first person *watashi*, past tense, written rather than spoken, fond of one
long simile per passage. He calls the adults *my uncle*, *my aunt* (the plain kinship words),
never "Uncle" and "Auntie"; he calls his young self "I", never "Boku".

The rule (Jay: *"I agree"*): plain, composed, slightly literary past-tense English; full
sentences; no contractions; keep the similes as similes and the sentence as one sentence
across its pages; no "little did I know" padding that is not in the Japanese. Think of a man
reading from his own memoir, not of a voice-over cracking wise. The child's lines next to it
stay short and spoken; the contrast is the device. The same voice carries the opening
monologue and the five epilogues, which have no text on the disc ([voice-only.md](voice-only.md)).

## 7. Sound: onomatopoeia, interjections, laughter, elongation

* **Real mimetic words are translated** into English description or an English sound word:
  *doki-doki* → "my heart was pounding"; *kira-kira* → "glittering"; *pika!* → "Flash!".
* **Invented sounds stay as sounds**, romanised: Boku's *hohe-hohe* (`E2805.1`), Shirabe's
  *bironcho*, *nashinko*. SETTLED BY CHARTER: there is nothing to translate. Two are spelled as
  English instead (Jay, 2026-09-27), because romanised they read as untranslated: Shirabe's
  *bayoyōn*, which carries "bye", is "Bye-yoyooon!"; Boku's word for the unreadable book,
  *ana-ana-bobon* — which the narrator says has no meaning (`E1706.4`) and which is also an
  item name (`exe@80046214.6`) — is "oobly-boobly-bon".
* **Insect and animal calls in the insect book** stay as the Japanese hears them
  (*kana-kana-kana*, *min-min-min*, *gii-chon*) — the entry is telling you how to recognise a
  sound the game then plays.
* **Interjections** become the nearest English noise: *un* → "Yeah" / "Mm-hm"; *ē?* → "Huh?";
  *hē* → "Ohh"; *wāi* → "Yay!"; *yattā!* → "I did it!"; *are?* → "Huh?" / "Wait...";
  *ā-a* → "Aww" / a sigh. Listed in the glossary.
* **Laughter** is spelled so that it reads as a laugh in English *and* matches the ear where
  it can: *hahaha*, *ahaha*, *gahaha*, *gyahaha*, *hehe*, *ehehe*, *kyahaha*, *nihihi* as is;
  *fufu(fu)* → "Hm-hm" (it does not read as laughter to an English eye); *gehehe* →
  "Geh-heh-heh". SETTLED (Q10.4, 2026-09-20); "Fufu" as heard was the rejected alternative.
* **Elongation.** The wave dash (263 uses) is not English punctuation. Stretch the vowel
  ("Nooo", "Hmmm", "smaaart"), or use a dash for a trailing call ("Boku-kuun!"). The wave dash
  is kept only on **sung** lines (§ 10).
* **Syllable-by-syllable spelling** (`E1701.7`, `E3042.3`) → the English words said slowly:
  the uncle's mysterious "Wolf... Girl."; Boku's emphatic taunt a full stop a word, "You. Pip.
  Squeak." (Jay, 2026-09-27).

## 8. Wordplay and words a child gets wrong — SETTLED (Q3, 2026-09-20)

The script has about twenty-five jokes that live in the Japanese language (listed in the
bible § Wordplay). Three kinds, three treatments:

1. **A child mishears or mispronounces a grown-up word** (*shishunki*, *ichiku*, *teiōgaku*,
   *yorugata*, *tōgeika* written in katakana because Shirabe is parroting it). The *event* is
   "a child mangles a hard word", so translate the hard word and mangle the English:
   "adolescence" → "Addle-essence?". This is translation, not localisation. SETTLED BY CHARTER.
2. **The joke is two English loanwords** (*derakkusu / derikēto*, `E1820.8`; *moratoriamu /
   puranetariumu*, `E2532.7`–`.8`). It works untouched. SETTLED BY CHARTER.
3. **The joke is a Japanese homophone** (*chō* = super / trillion / butterfly necktie,
   `E2205.3`–`.5`; *ame* = rain / candy, `E1840.0`–`.1`; *hana* = nose / flower, `E1920.2`–`.4`;
   *mashin* = measles / machine, `E1220.3`–`.6`; *chinpun-kanpun* "sounds like a panda's name",
   `E2532.5`–`.6`). **Translate literally and let the Japanese word show in the line** —
   "A *chō*-tie!" / "A trillion ties?" / "Chō as in butterfly. A bow tie." Jay: *"Yes,
   (a) is right."* The player can hear the word being repeated, and the charter's reader would
   rather see the joke than be handed a different one. The rejected alternatives: a new
   English pun (localisation), or translating straight and losing the joke (what Google
   Translate would do). Q3 shows all three on the same lines.

## 9. Punctuation and typography

* **The speaker label is data, not text.** In the Japanese it is inline (`おじ「…」`). It
  changes mid-scene when a stranger is named (*the boy* → Guts at `E0551.16`, *the woman* → Saori at
  `E1861.28`), is joint once (`E1304.10`), and is absent on choruses. Translation files carry
  it as a **parsed field** (as the samples do), never inline in the English — Jay: *"We
  definitely want to parse the label in our translation files, because that will be convenient
  for the translation prompts."* English labels: Boku, Uncle, Aunt, Moe, Shirabe, Guts, Fat,
  Specs, Father, Monk, Boy, Woman, Saori, Narrator, All.
  **On screen — SETTLED (Q7, 2026-09-20) as an early default, explicitly revisitable:** the
  renderer draws labelled dialogue in the original's style, label and marks — Jay: *"Ideally,
  we'll retain the same style as the original, including labels and marks"* — and the
  translation text itself carries **no quotation marks**, so that the marks are the renderer's
  to draw, restyle or drop. It is revisitable because of the cell cost: Jay: *"Uncle + two
  quotes is 4 characters in Japanese and much more in English, so it is expensive. I think we
  may need to default to something early but be willing to go back to it."* Whether the marks
  are the 「 」 glyphs or English quotation marks, and whether the label sits inside the box, is
  the dialogue band's decision. Narration (『 』 in the Japanese) is
  unlabelled and set apart by the renderer; system messages ("Got the fishing rod.") plain.
  **The one exception is `movies.txt`** (FMV-07, Jay, 2026-09-24): a movie has no original
  text for the renderer to read the marks from, so the adult Boku's narration cues carry
  `『 』` in the English, one pair per sentence however many cues it spans (Jay, 2026-09-24,
  FMV-09; `translation/README.md` § movies.txt).
* **Quotation marks around a word named inside a line are allowed** — SETTLED (Q7, Jay,
  2026-09-23): *It's written "poem" and pronounced "Shirabe"* (`E0177.1`), a word written on a
  sign, a word someone asks the meaning of. Straight double quotes; the font has them. What
  stays unquoted is the utterance itself, above.
* **One utterance is sometimes split across two messages** with the closing bracket in the
  second (`E1405.1`–`.2`, `E2231.1`–`.2`, `E2303.3`–`.4`): a silent beat, then the speech. The
  pair is translated as one sentence and must stay in order.
* **Sentence punctuation is added.** The Japanese uses spaces and line ends instead of commas
  and full stops. English gets normal punctuation, including final full stops.
* **Ellipsis** (1,055 uses): three full stops, no space before, one after mid-sentence. A
  silent message (`……`) → "......". A leading ellipsis is kept ("...Nine.").
* **Emphasis:** capitals for a shouted word, sparingly. No italics are assumed to exist.
* **Full-width Latin and digits** in the source (`ＺｚＺ`, `７`) → ordinary characters.

## 10. Songs and verse

* The aunt's made-up ditties (`E1120.0`, `E1920.0`) → translated, unrhymed, with the wave dash
  kept at the held notes so they read as sung: "An important, important letter~".
* **The uncle's tanka** (`E2515.0`, repeated `E2712.0`) is the one formal poem, in classical
  grammar, 5-7-5-7-7. He passes it off to Boku as "autumn's coming"; it is about his dead son
  and the kiln. Translate it as five short lines, literal, without forcing syllables, keeping
  it possible to read innocently; his self-rebuke after the second recital puns on *utsuwa*
  (vessel / a person's capacity) and a potter can say "small vessel" in English too.
* **The insect book** (`hhon@5328.*`) is sixty short entries in Boku's own voice, several in
  5-7 rhythm. Keep them as light verse in short lines, a child's observations; do not pad them
  into encyclopedia prose.
* **The 1942 letter** (`E2303.7`) is a schoolboy's formal written Japanese, read aloud by Moe
  over thirteen pages. Earnest, slightly stiff, period English; "Spring, Showa 17" (§ 11).

## 11. Numbers, dates, units — SETTLED BY CHARTER except the era year and eyesight

* Metric stays: 120 m, 5 cm, 1,200 degrees (Celsius is implied). School years stay Japanese:
  "third grade". Eyesight is converted exactly to the Snellen scale English readers know
  (decimal 4.0 = 20/5, 2.0 = 20/10; `E2120.0`, `E2440.2` — the impossible number is the joke, and
  only a reader who knows the scale gets it; Jay, 2026-09-27).
* Dates: "August 1". The save title and diary date are digits + month + day composed by code
  (`research/text-outside-events.md` § "Text made at run time") — word order there is an
  engineering question, flagged in the bible § Engineering notes.
* **Era year — SETTLED (Q10.2, 2026-09-20):** the letter is dated *Shōwa 17, spring* →
  "Spring, Showa 17", no gloss. Jay: *"'Showa 17' is what someone back then would write and
  the audience can Google it."* The letter itself says the country is at war with America, so
  the reader is not lost. "Spring 1942" was the rejected alternative.
* Kanji numerals → digits above ten and for measurements; words for small counts in speech.

## 12. Period attitudes and rough language — SETTLED BY CHARTER

Translated at full strength, without comment: "you build models even though you're a girl"
(`E0113.2`), "boys mustn't cry" (`E3180.0`), stewardess / pilot (`E2820.3`), the bath scene
and its aftermath (`E2104`–`E2109`), Saori's kiss and Boku's one-word question (`E6004.24`),
the boys' taunts (`E2140.1`, `E2850.2`), "Mammoth Fatso". One word needed a decision because
the honest rendering is a slur: Boku, told that Saori is "like a well-bred young man, but a
beautiful young woman", asks "*...okama?*" (`E1720.4`). SETTLED (Q10.3, 2026-09-20): "...A
drag queen?" — a nine-year-old's TV word in 1975, neither sanitised nor sharpened.

## 13. Pages and lines — content level only

* **One Japanese page = one English page, in the same order.** Voiced messages turn their own
  pages on a frame count matched to the recording. A translator may not merge, split or
  reorder pages; may not move a clause to the next page to make it read better.
* Inside a page the Japanese is at most 3 columns × 16 cells. English will need more; the
  charter says that is solved by engineering. **Do not shorten to fit.** Do, however, write
  tight: a page is a breath of speech, and a subtitle that is still being read when the voice
  has moved on has failed.
* Because a page is a breath, **each page should be a clause that can stand for a second on
  its own**: end pages on a natural pause even where the Japanese sentence runs on, using "..."
  or a dash to carry the sentence over. Japanese puts the verb last, so long sentences often
  have to be re-ordered *within* the message; keep each page's *content* with its voice segment
  as far as English allows, and flag (`#` note) any page where what is on screen is not what is
  being said.
* **Choice menus** are hard-coded vertical lists; the first row is sometimes the question
  (`E0020.0`). Options are translated in full (the dinner quiz's longest dish is thirteen cells
  of Japanese and about forty letters of English — an engineering note, not a reason to
  abbreviate).

## 14. Text in textures

* **The picture diary** (94 pages, `research/textures.md`) is Boku's own writing: almost all
  kana, five to eight words a line, plain statements and one exclamation. English: a
  third-grader's sentences, short and declarative, correctly spelled — the Japanese is not
  misspelled, it is just young. "Mom is having a baby, so it's a big fuss! I'm staying at
  Uncle's house. I wonder if there will be lots of fun things?" (*isōrō* is "staying at" in
  Boku's own mouth, not "freeloader" — glossary § 3.) Hand-lettered, not typeset.
  SETTLED (Q10.10, 2026-09-20).
* **Insect book and kite book covers, the calendar, signs**: translated in place when redrawn.
* **Signs read out by the narrator** (`E1707.0`) are translated in the narration; the sign
  texture itself can stay Japanese.
* Partly-legible text is translated as partly legible (`E8060.0`, a weathered sign with most
  characters missing): keep the gaps.

## 15. What stays in Japanese with no gloss

Names of people, animals and settlements (Q4, Q5); *-kun / -chan / -san*; *Onee-chan,
Onii-chan, -neechan* (Q1); *itadakimasu, gochisōsama* (Q2); the cicadas and the singing insects
by their Japanese names, while butterflies, beetles and dragonflies are English (Q6, glossary
§ 4a); the fish *iwana* and *yamame* (Q10.11); real sumo techniques in the bug-sumo move list
(Q10.9); *mizore* syrup (Q10.7); dishes that English-language Japanese cooking already calls
by name (*tonkatsu, karaage, gyoza, katsudon, oyakodon, tempura, sashimi, sushi, omurice,
nikujaga, korokke*); *tanuki, tengu, oni, kappa* (as in *kappa-maki*), *jizō*, *yukata, futon,
kotatsu, tanabata, tenkara*; invented words (but § 7's two spelled as English). Everything else is English — including
*satoyama*, rendered by sense (Q10.8; Jay, 2026-09-21: "somewhere this rural" where the father
says it, glossary § 7). All SETTLED 2026-09-20.
In-line glosses are allowed only for § 8 kind 3; there are no translator's footnotes on screen.
A glossary screen or booklet for the player is an idea, not a plan.

## 16. English inside the Japanese

* The monk's party-piece English and German (`E1203.8`, `E1204.0`) is written in katakana and
  he translates himself. Keep it visibly *his*: "HAU ŌRUDO ĀR YŪ?" is too much; "How-oldo...
  are-you?" is the weight — then his own translation follows as in the source. SETTLED
  (Q10.5, 2026-09-20; Jay: *"Yes, definite."*).
* Loanwords used as ordinary Japanese (*chansu*, *purezento*) are just English.
* **A Japanese gloss on an English word is dropped by default**, because it would gloss a word
  into itself (`E0650.11`). This is the only deletion this guide allows; each instance carries
  a `#` note in the translation file. SETTLED (Q10.6, 2026-09-20) with one exception Jay
  added: *"If the gloss is characteristic and funny for the character, it could stay"* — i.e.
  when the gloss is the speaker's own words and the joke is in their saying it, translate it
  as their line rather than deleting it. A player-aid gloss in the text (the `E0650.11` case)
  is not that, and goes.

## 17. Speech with no text on the disc — SETTLED (Q11, 2026-09-20)

The opening monologue, the five epilogues and the other speech-bearing voice-only clips are
translated into tracked files under this directory, in the narrator's voice where they are
his (§ 6); how they reach the screen is decided later, with engine-drawn subtitles preferred
over re-encoded FMV frames. Jay: *"let's go with (b); we'll figure out later whether we put
subtitles in the FMV or do it within the engine. Within engine is better."* The list of
sequences and their ids is [voice-only.md](voice-only.md).

## 18. Em dashes — SETTLED (Jay, 2026-09-21)

* SETTLED: an em dash is a habit of machine-written English, not of this script. Use one only
  where the Japanese itself breaks or trails the line with a dash-like mark (a `――`, a cut-off
  utterance the original marks), never for an aside, a pivot or emphasis the Japanese carries
  with a particle or a comma. When in doubt, a comma, a full stop or an ellipsis the source has.
  The lint warns on every em dash; a warning is a prompt to check the source, not a
  ban.

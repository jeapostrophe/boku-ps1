# Story bible (PLAN `TRN-01`)

What a translator needs to know about *Boku no Natsuyasumi* (PS1, 2000) before touching a
line: where and when it is, who everyone is and how they talk, what happens on which day, what
the game is about, and the places in the text where the Japanese language itself is the
subject. Policy is in [style-guide.md](style-guide.md); fixed renderings in
[glossary.md](glossary.md). CC BY-SA 4.0.

**Every claim carries its source:** [script] — read in the decoded text of this disc, with line
ids (the whole event script, 677 events / 2,686 messages, and all 34 text arrays were read for
this document); [walkthrough] — jooey's GameFAQs guide v0.36, or [xneo] — xneo.jp's Japanese
walkthrough; [review] — Tim Rogers' Action Button review (auto-captions); [web: file] — a file
under the local `reference/web/`, listed with its URL in `reference/SOURCES.md`; [inference] —
ours. **Where a secondary source and the script disagree, the script wins**, and the
disagreement is recorded in § 9 so nobody re-imports the error.

## 1. Setting

* **When.** August 1–31, Shōwa 50 (1975) [web: archive-scei-bokunatsu-portable-story]. The
  script never states the year; it fixes it indirectly — the aunt was about Boku's age when the
  Pacific War ended, "thirty years ago" (`E1420.2`, `.5`) [script]. The designer, Kaz Ayabe, kept
  the era deliberately vague while writing ("late Shōwa 40s to the start of the 50s") and the
  year was pinned down afterwards [web: famitsu-2006-ayabe-interview]. That is why the in-game
  calendar is not 1975's: the script has a Friday the 13th (`E1331.0`, `E1341.0`), and
  13 August 1975 was a Wednesday [inference]. Translate what is written.
* **Where.** A fictional mountain valley, **Tsukiyono** (月夜野), above the village of
  **Sagi-no-sato** (鷺の郷) [script: `E0210.1`, `E0001.0`]. Sony's own copy puts it in "northern
  Kantō" [web: archive-scei-…-story]; the model is Tsukiyono in Dōshi village, Yamanashi, where
  Ayabe recorded all the ambient sound and whose small wooden bridge over the Dōshi river became
  the bridge by the house; it is *not* the better-known Tsukiyono in Gunma
  [web: ja-wikipedia-bokunatsu, dengeki-2015, famitsu-2015]. The geography is a composite, not a
  map: there is an expressway overhead, a sea within a child's walk, and the sun sets into that
  sea (`E1406.14`) [script].
* **The house.** A farmhouse built in the middle of the Meiji era in the Kanazawa region,
  bought and moved here by the previous owner (`E0712.2`) [script]. It has an *engawa* and high
  ceilings and needs no electric fan (`E0112`). Home-made milk from a cow that wandered in as a
  stray (Nora), a dog brought from Tokyo (Ken-bō), a vegetable plot, corn and watermelon fields,
  a workshop and a climbing kiln. No doctor anywhere near (`E0406.2`); three television
  channels (`E1941.2`, `E2041`) [script].
* **The household came from the city.** Yūsaku and Kaoru married in Tokyo seventeen years ago —
  the registry office was Suginami's (`E2212.1`); she was a photographer's assistant there
  (`E0445.4`, `E3022.0`); she grew up in Otaru, Hokkaidō (`E1420.2`); an arranged marriage, and
  she is a year older, which he found out at the last minute (`E2210.4`) [script]. This is why
  **nobody in the house speaks dialect** — and neither do the village boys (style guide § 5).

## 2. Premise and frame

A nine-year-old city boy is left for the month with his father's sister's family because his
mother is about to give birth (`E0173.0`, `E2004.7`) [script]. The game is told twice at once:
the child acts and speaks in the present, and **his adult self narrates in the past tense**
(51 narration messages, bracketed 『 』, speaker slot 255) [script]. The narrator is looking back
from about 2000 [review; web: ja-wikipedia-bokunatsu says "25 years on"]. His opening
monologue and the five epilogues are in the FMVs and have **no text on the disc at all**; they
are translated anyway, into tracked files, with delivery decided later (QUESTIONS Q11, ruled
2026-09-20; the list is [voice-only.md](voice-only.md); see also § 8).

Each day: rooster, **radio calisthenics** (an FMV), breakfast at 7, free time from 8, the
uncle's call that playtime is over (`E0190.0`, `E3007.0`), dinner at 18, the living room, an
optional bath (`E0020`), the **picture diary** at the desk upstairs — which is also the save —
and sleep [script; walkthrough]. Time moves only when Boku changes screen [walkthrough].
Breakfast and dinner open and close with the shared chorus (`E0006`/`E0007`/`E0009`/`E0010`);
65 meal events hang a conversation on it [script; research/event-scripts.md]. Between 14:00 and
17:00 the aunt, in the kitchen, plays **guess-the-dinner** (`E0221`: three dishes a day, 31
tables, a native routine picks the day's); after dinner she announces the menu (`E4028`)
[script].

What Boku does with the month decides which of **five endings** plays: fifteen events count,
and 0–3 / 4–6 / 7–9 / 10–12 / 13–15 of them select the epilogue [xneo]: the valley drowned by a
dam; a programmer at an electronics firm; the sisters' marriages; a potter like his uncle; a
novelist [web: gameyarou-bokunatsu-endings; review]. The fifteen are listed in § 4.

## 3. Cast

Slots and labels are from `research/event-scripts.md` § Speakers. Ages marked [walkthrough] are
jooey's (the manual's, presumably); the script gives school years.

### Boku (ボク) — slot 0, label ボク, 742 lines
Third-grader, nine ("*kokonotsu*", `E1203.9`). Family name **Kubota** (`E2904.1`) [script];
Ayabe chose it so that *Kubota Boku* is a palindrome in kana [web: ja-wikipedia-bokunatsu]. His
teacher is Nakajima-sensei (`E1861.27`). He arrived with one small bag his father packed — one
shirt (`E0121.1`, `E3030.1`). Cannot swim (`E1405`), is afraid of snakes (`E2206`), **hiccups
when frightened** (`E0405.1`; the narrator: "my usual habit"), reads a lot (`E0653.1`), plays
bench in baseball (`E1251.1`), collects Rider cards his father started (`E1452.3`).
**Register:** *boku* in katakana; plain-polite child's Japanese, *da yo / nan da*, "un" for yes;
always *Oji-chan, Oba-chan, Moe-neechan*; rude only to Shirabe (*omae, chibi-musume*) and
cheeky to Saori (*anta*). Literal-minded and deadpan: his quiz-show "*Naze deshō?*" / "*Nan
deshō?*" is a tic (`E0832.8`, `E1506.0`, `E1762.0`, `E6000.4`); he mishears adult words
(*ichiku, shishunki, mashin, yorugata, derikēto*).
> ボク「ホームシックの意味が分かったら、ホームシックになってみたくなったよ」 (`E0520.9`)
**In English:** short, grammatical, earnest sentences; polite to adults; no slang, no baby talk.
Let the deadpan be deadpan.

### The narrator (adult Boku) — slot 255, 『 』, 51 lines
*Watashi*; written, past-tense, reflective; one extended simile per passage; *oji / oba* for
his uncle and aunt; never says "Boku".
> 『それが夜のホタル沢へ行くたった一度のチャンスだった』 (`E0502.7`)
> 『こういうこともあるさ…そう思いながらも、なんだか胸が苦しかった…』 (`E3050.1`)
**In English:** style guide § 6 — a man reading from his memoir; no contractions; no added
irony. He is sometimes drily funny at his young self's expense (`E0471.4`: Shirabe as "my first
encounter in life with a terribly high-maintenance creature"; `E1706.4`: "incidentally, this
word has no meaning whatsoever").

### Sorano Yūsaku (空野優作) — Uncle; slot 1, label おじ, 381 lines
Potter, 40 [walkthrough]; his studio is the Tsukiyono Kiln (`E0210.1`). Easy-going, lazy about
everything but the kiln ("the easy way is the best way", `E0312.0`), home by four, asking for
beer his wife will not fetch (`E0113.6`, `E1012`, `E1013`, `E2112`). Makes the kites, the
fishing fly, the swing. Lays down the rules of the house and then is absent on the one night
it matters (day 5). Grieves sideways: the fireworks "he loved" (`E0912.0`), "three years
already" (`E1513.1`), the tanka (`E2515.0`).
**Register:** to Boku, gentle and **mock-official** — *desu/masu* for rules and appointments
("*tachiiri kinshi desu*", "*tōban ni kettei!*", "*…suru koto!*"), self-reference *Oji-san*;
to his wife and alone, an ordinary man's *boku* (`E1904.9`, `E2712.0`); to his daughters,
*Otō-san*.
> おじ「この時間、ここから先は立ち入り禁止です … これはおじさんちの決まりなんだから」 (`E0002.1`)
> おじ「何事も楽チンなのが一番だよ」 (`E0312.0`)
**In English:** warm, unhurried, a little teacherly; official phrasing as a game he plays with
the boy; "Uncle" for himself with Boku, "I" otherwise.

### Sorano Kaoru (空野薫) — Aunt; slot 2, label おば, 335 lines
Boku's father's younger sister, 41 [walkthrough]; changed Boku's nappies (`E0181.0`). Up before
radio calisthenics with the washing and breakfast done (`E2720`). Former photographer's
assistant: she photographs the children with "What does Dad like best?" — "Cheese!" (`E0445.5`).
Teasing, frank, unshockable (her three wake-up lines after Boku knocks himself out,
`E4022.2`–`.4`). Carries the month's two great speeches — the American soldier and the kitten
(`E1420.2`–`.5`) and what it is to be happy (`E3004.4`) — and the fever night.
**Register:** standard feminine speech (*wa, no yo, kashira*), the chuckle *fufu* (36 uses
script-wide, mostly hers), self-reference *Oba-chan* with Boku, *watashi* otherwise; calls her
husband *Yū-chan* or plain *Yūsaku*, her daughters *Onee-chan* and *Shirabe(-chan)*.
> おば「空野家の旗をずらっと並べて、我が家の主婦力を誇示しているような…」 (`E0220.2`)
> おば「お兄ちゃんはお兄ちゃん　ボクくんはボクくん」 (`E2805.9`)
**In English:** warm and quick, never gushing; "Auntie" for herself with Boku.

### Sorano Moe (空野萌) — slot 3, label 萌, 312 lines
Eldest daughter, 15, third year of middle school, an exam student (`E0930.5`). Learning the
clarinet from a friend for the autumn school festival (`E0332.1`); practises on the veranda at
night, improving as the month goes; the tune is "My Bonnie" [web: ja-wikipedia-bokunatsu].
**Her arc is the month's spine:** pressing flowers for someone (day 7), "writing something
very important" (10), posts a letter (11), waits (14–17), the reply comes (18), she stops
eating, declares she will give up school and stay in the valley for ever (20, `E2006`), takes
Boku into the bath and tells him she was jilted (21), and is brought back by the 1942 letter
Boku finds in the air-raid shelter and she translates with the English she hates (23–24:
`E2330`, `E2303`, `E2401`). She will leave for high school and live alone in spring (`E2432`).
**Register:** tomboyish and musing — *da na, na n da na, no da*, big laughs (*gyahaha*),
*nantsū ka*; *watashi*, or *Onee-chan* to Boku; *Boku-kun*, once a teasing *anta* (`E0832.2`).
> 萌「な〜んにも考えずに静かに暮らしていければな〜　そして気がつけば…いつのまにかおばあちゃんになってました」 (`E0780.0`)
> 萌「大人はこれをモラトリアムと呼ぶんだよ…」 (`E2532.4`)
**In English:** a thoughtful teenager thinking aloud; wry about herself; no valley-girl, no
period slang she does not use.

### Sorano Shirabe (空野詩) — slot 4, label 詩, 310 lines
Second daughter, second-grader, 8 [walkthrough]; "written *poem*, read Shirabe" (`E0177.1`).
Smallest in her class — first in line (`E0541.4`) — hence the banned nickname. Few friends
because she takes other children's lunch (`E0940.4`); studies ants "to learn how to rule"
(`E0640.2`); will be an idol singer and drive a Benz. Was in kindergarten when her brother
died (`E1404.4`); sunflowers are his flower and become Boku's (`E1404`, `E2902.7`, `E3005.7`).
Her contempt thaws into the day-30 disappearance.
**Register:** an eight-year-old playing a lady: *wa, no yo, kashira, desu no yo*, "*redī*",
self-reference by name; *anta* for Boku throughout; coinages (*bayoyōn, bironcho, nashinko,
patchin-wāku, murasaki chū-chū*) and adult words worn a size too big.
> 詩「レディーが優雅な食後のひとときを楽しんでいるというのにさ」 (`E0241.2`)
> 詩「女はいつの時代にも悪にひかれるものなのね」 (`E2441.3`)
**In English:** prim, bossy, over-grown-up diction; third-person "Shirabe"; the made-up words
stay made up.

### The son who died — "Onii-chan"
The Soranos' only son and middle child: Shirabe's "onii-chan" (`E1404.3`) and the "cute little
brother" Moe lets slip that she had (`E2105.8`) [script]. Loved aeroplanes (the model in the
workshop window, `E0510.1`), sunflowers (`E1404.5`, `E2920.4`) and the Sagi-no-sato fireworks
(`E0920.1`); died three years ago (`E1220.1`), cause never stated — Boku had measles and missed
the funeral (`E1220.3`). **He is never named.** The memorial is **August 12**
(`E1101.2` on day 11: "tomorrow"), the grave visit August 15. His hand-me-downs (`E0121.5`),
his insect kit (`E0114.5`), his cap in the hall (`E8009.0`), the swing unused for three years
(`E1602.3`). Boku's question on the fever night (`E2805.8`) and "Congratulations, Onii-chan"
(`E2907.2`) close the thread.

### Saori (沙織) — slot 5, label 女性 then 沙織, 155 lines
University student in Sendai, natural sciences (`E1861.26`); the family's **Wolf Girl** and
Shirabe's **Bath Lady**; camps by Dragon God Pond every summer with a tent full of books and
her own flower paintings, trying to photograph a Japanese wolf with a tripwire camera. As a
small child living at the foot of the mountain she got lost here and a howl sent her running
into the arms of the search party (`E6001.12`–`.19`). Boku baits her camera with sugar water
for the thing *he* has met in the woods; the photograph comes out (day 23–24, `E2306`), and she
will tell no one (`E6000.7`). Kisses him for admitting he ran from a snake (`E6004.15`). Leaves
on day 28. Aunt: "like a well-brought-up young man who is a beautiful young woman" (`E1720.3`).
**Register:** blunt masculine endings with Boku (*da na, daro, butsu yo, kuso-gaki*), polite
*desu/masu* with the adults; *Kā-san* for the aunt.
> 女性「自分から名乗りなさいよ、少年一号」 (`E1861.2`)
> 沙織「達者でな、くそガキ」 (`E2760.0`)
**In English:** dry, clipped, affectionate insults; then suddenly lyrical ("a sad, lonely
cloud", `E6004.5`).

### The three boys — slots 6, 7, 8
**Guts** (ガッツ; label 少年 until `E0551.15`), fifth grade, boss of the secret base under the
expressway and chief watermelon thief; *ore*, *ze*, *daro*; calls Boku *Boku-chan*; keeps his
word; his family is selling their rice fields and he will have to leave for the city
(`E2951`). **Fat** (ファット), fourth grade; *ore-sama*; crude, greedy, in love with *Moe-san*.
**Megane** (メガネ), second grade, Shirabe's classmate and victim; a careful *boku* and *kimi*;
bookish non sequiturs (Narnia, Dolittle, Miffy's mouth); will build the village a library.
No source gives them real names [web]. Their 74 + 48 + 41 lines are mostly one-line chats
gated by a counter (flag 72) and three rotating sets of bug-sumo tips.
> ガッツ「男と男の約束だからな、破ったら、しっぺ百回ね」 (`E0551.12`)

### Others
**Father** (父, slot 9, 9 lines) — Kubota; "frankly unimpressive" to the narrator on day 1
(`E0180.0`), mysteriously full of vigour on day 31 (`E3171.1`); folksy (*nantsū ka*, *desu wa*).
**Mother** — Yuzuki (柚木), never seen. **The monk** (お坊さん, slot 10, 7 lines) — nearly sixty,
hearty, shows off scraps of English and German (`E1203.8`, `E1204.0`). **Ken-bō**, the old dog
(talk target 11); **Nora**, the cow. **The thing in the woods** — never named by the game; Boku
calls it the *henteko obake*; the howl is a voice-only clip (`E0405.5`, `E1306`, `E1905`).

## 4. The month

Forced events are from the script (event id ÷ 100 = day); conditional ones are dated by their
condition trees and cross-checked with [xneo] and [walkthrough]. **★** marks the fifteen
ending events [xneo].

| day | what happens | ids |
|---:|---|---|
| 1 | Arrival; introductions in a relay of close-ups; the room upstairs and the sunned futon; the uncle promises, then leaves on the desk, a hand-me-down insect kit in a model-aeroplane box | `E0171`–`E0186`, `E0114`, `E0107` |
| 2 | Appointed morning-glory captain ★(nine days of bloom); finds the secret base and the wrecked watermelon — and says nothing at dinner | `E0202`, `E0254`, `E0255`, `E0204` |
| 3 | Fishing rod; corn harvest ★; Firefly Creek forbidden after dark | `E0301`, `E0306`, `E0384`, `E0303` |
| 4 | Shirabe's guided tour ★ — river, Jizō, nectar flowers, the photograph; the watermelon thief and the howl; shaved ice | `E0401`, `E0442`–`E0445`, `E0405`, `E0406` |
| 5 | Guts and the pact; the uncle is out: the one chance to see the fireflies ★ | `E0551`, `E0502` |
| 6 | Oversleeps (no calisthenics stamp); the aunt found a firefly in his futon; the hive can come down (any day once he has the rod — `E0205` has no day of its own, and this is when it usually happens); Fat and Megane; sugar bait | `E0605`, `E0620`, `E0205`, `E0650`, `E0604` |
| 7 | The hill → kites; Moe's flowers in the forest ★ | `E0701`, `E0733`–`E0786` |
| 8 | The old axe; "Boku-kun unbanned" from the sisters' room; fireworks from his window | `E0814`, `E0830`, `E0805` |
| 9– | The giant fish, Ken-bō's fur, the fly ★(catch it); the satellite (day 10: the narrator's sentence begins in movie M120 and ends in the first line of the satellite event (`E1008.0`), whose English picks it up as "...a satellite, flying quietly on, as if gliding."; translation/movies.txt, M120); the log bridge (five days of chopping) | `E0906`, `E0904`, `E1006`, `E1008`, `E0807` |
| 11 | "Tomorrow is the anniversary"; Moe posts her letter, buys salad oil instead of mirin; yukata and sparklers | `E1101`, `E1102`, `E1121`, `E1104`, `E1171` |
| 12 | The monk; "When did he die?" | `E1202`–`E1204`, `E1220` |
| 13–14 | Cloud shapes at dinner → with Shirabe to the Cape of Winds ★: sunflowers, the beach, asleep on the cape, sunset. The aunt's war story. First meeting with the thing in the woods | `E1304`, `E1402`–`E1406`, `E1420`, `E1306` |
| 15 | Alone all day (grave visit); the quiz at breakfast; the whale's ear bone and the uncle's story; whale dream | `E1501`–`E1504`, `E1506` |
| 16 | The swing, after three years; Nora lowing | `E1602`, `E1612` |
| 17–18 | "The Bath Lady's back"; the camera in the woods; Moe's reply arrives; Saori; Guts's secret weapon (a mantis) ★ → the secret shortcut | `E1701`, `E1761`, `E1802`, `E1861`, `E1750`, `E1754` |
| 19–21 | Moe absent from table; "I saw a ghost"; the family argument; Saori comes for a bath; the bath with Moe; "what your heart is for" | `E1901`, `E1904`, `E2006`, `E2004`, `E2104`–`E2109` |
| 22 | Wedding anniversary, sushi; the vice-principal's buried treasure; the snake ★(the skin); Saori's kiss; the sugar-water trap | `E2202`–`E2204`, `E2206`, `E6004`, `E2161` |
| 23–24 | The wolf photograph ★; the book from the shelter → Moe reads the 1942 letter at dinner ★; "I'll go to school after all" | `E2306`, `E2305`, `E2330`, `E2303`, `E2401` |
| 25–27 | No rain all month; the kiln lit, the tanka, the all-night firing; the sun shower ★; Mt. Teppen ★ and "I'm glad I came"; the kiln opened; Saori says goodbye | `E2507`, `E2514`, `E2515`, `E2605`, `E2505`, `E2504`, `E2760` |
| 28 | Saori gone; the boys ask when he leaves; fever | `E2850`, `E2803`, `E2805` |
| 29 | Morning-glory photographs; goodbyes at the base; the phone call — a brother; sunflower dream | `E2902`, `E2950`, `E2904`–`E2907` |
| 30 | Shirabe missing; the ribbon; found in the sunflower field ★; the bouquet; the aunt's happiness; the base is empty | `E3001`, `E3006`, `E3042`, `E3005`, `E3004`, `E3050` |
| 31 | Father arrives transformed; "Hold me"; the rule at Auntie's house | `E3101`–`E3182` |

★ also: all eight kites.

## 5. Themes and tone

* **Loss that is lived with, not revealed.** The dead son is never a twist; he is a cap on a
  hook and a swing nobody hung. The aunt answers Boku's blunt question in two words
  (`E1220.1`). Translate the plainness. [script; review agrees]
* **Everyone is about to leave.** Moe for school, Guts for the city, Saori for Sendai, the
  fish, the morning glories, the summer; Shirabe says it outright (`E2940.5`). The narrator's
  "these things happen" (`E3050`) is the book's motto.
* **The war, thirty years on** — the aunt and the kitten, the 1942 letter (a boy hiding his
  English dictionary, hoping to tell his future self what he felt), the uncle's "the summer the
  war ended felt like this" (`E2912.1`). Undramatic, and at the dinner table.
* **The countryside is already going:** pesticides and fireflies (`E0502.3`), concrete
  (`E0112.4`), Saori's "new towns washed in detergent" (`E6004.19`), a rare butterfly Boku
  "will never allow" to vanish (`hhon@5328.15`), the expressway overhead, the ending in which
  the valley is dammed [web: gameyarou].
* **Comedy of a literal child among ironic adults** — and bathos placed *after* the tender
  moments (`E2805.17`). Do not smooth it away.
* **Shōwa texture as the point**: school lunches, Rider cards, three TV channels. The audience
  came for it (charter).

## 6. Wordplay and language-dependent lines

The working list for style guide § 8 (kinds 1–3) — every one needs a translator's note. Kind 3
is translated literally with the Japanese word showing in the line (Q3, ruled 2026-09-20).

| ids | what | kind |
|---|---|---|
| `E0177.2` | *tōgeika* in katakana: a word Shirabe is parroting | 1 |
| `E0340.1`–`.2` | *gasatsu*: Boku does not know the word; Shirabe's definition is circular | 1 |
| `E0640.2`–`.3` | *teiōgaku* → "*tē-ō?*" | 1 |
| `E0712.3` | *ichiku* (moving a house) | 1 |
| `E0720`, `E0740.1`–`.2` | bush-warbler droppings; Shirabe "knows": she is thinking of the idiom *kingyo no fun* (a hanger-on) | 3 |
| `E1220.3`–`.6` | *mashin* (measles) heard as *machine* | 3 |
| `E1820.8`–`.10`, `E2203.0`–`.2` | *deluxe* for *delicate*; on day 22 they swap | 2 |
| `E1840.0`–`.1` | rain of blood / blood candy (*ame*) | 3 |
| `E1912.3`–`.4` | *shushinki* / *shishunki* | 1 |
| `E1920.2`–`.4` | humming (*hana-uta*, "nose song") / flower song | 3 |
| `E2205.3`–`.5` | *chō*: super / trillion / butterfly (bow) tie — **visible only in writing**; the three are homophones in the audio | 3 |
| `E2210.6` | "wearing a cat" (feigning innocence) extended to a dog and a tanuki | 3 |
| `E2430.1` | *yorugata* (night person) | 1 |
| `E2532.4`–`.8` | *moratorium* / *planetarium*; *chinpun-kanpun* "like a panda's name" (Kang Kang and Lan Lan arrived in 1972) | 2, 3 |
| `E2641.2` | weather-telling by kicking off a *geta* — "maybe it fails because it's a sandal" | culture |
| `E2712.0` | *utsuwa ga chiisai* — small vessel / small man, said by a potter | carries |
| `E1503.5` | the three four-character idioms Boku can choose to describe his day alone (the second means a debauch); the uncle: "you know some hard words" | 3 |
| `E4028.17` | Ōshō (king) Sushi's Hisha (rook) set | 3 |
| `E1861.3`–`.5`, `.27` | *Boku wa Boku* | style guide § 1 |
| `E1420.0`, `E2320.0` | the title in dialogue | style guide § 1 |
| `E1701.7`, `E3042.3` | spelling a nickname out syllable by syllable | § 7 |
| `E8060.0` | a sign with most characters weathered away — settled (review, 2026-09-20): an English notice skeleton with the gaps kept, the one legible word-start showing as sound ("taka"); if the sign texture is ever redrawn it should match | § 14 |
| `hhon@5328.10`, `.40` | *chō* puns in the insect book; `.48`/`.49` the swapped names; `.3`, `.21`, `.29`, `.33`, `.37`, `.39`, `.44`, `.46`, `.51` entries about the Japanese name | glossary § 4a |

## 7. Map bases → places

`research/event-scripts.md` flags this as missing from the disc data. Established from what is
said and found in each base [script], and the walkthroughs' route descriptions. *?* = uncertain.

| base | place | evidence |
|---|---|---|
| G01 | living room (the uncle's evening seat; bookshelf) | `E0112`, `E0022` |
| G02 | dining room — meals | meal events; `E8000`–`E8002`, `E8050` |
| G03 | kitchen (fridge, sugar; the aunt 14–17 h) | `E0221`, `E4029`, `E0670` |
| G04 / G05 | washroom / bath | `E0020`, `E8005`, `E2061` |
| G06 | TV room (Shirabe in the evenings) | `E0141`, `E0305` |
| G07 | foot of the stairs / hall | `E0114`, `E2106`, `E3043` [xneo] |
| G08 / G09 | hall with the telephone / front entrance | `E2906`, `E8009`, `E1202` |
| G10 / G11 | the room with the family altar, and the room beside it | `E1203`, `E8011`, `E8010` |
| G12 | upstairs landing | `E0835`, `E4001` |
| G13 / G14 | Boku's room (door side / desk, window, futon) | `E0183`, `E0184`, `E4027`, `E0805` |
| G15 / G16 | the sisters' room / Moe's bed | `E0830`, `E1830` |
| G17 | the veranda (*engawa*) | `E0402.12`→`MAP G17`, `E0832`, `E1171` |
| G18 | ? reached from G07 with an FMV — toilet? | `E4015` |
| H01–H03 | front of the house, gate | `E0171`–`E0181`, `E3171`– |
| H04, H09, H10 | garden corners where Shirabe watches ants | `E0340`, `E0140`, `E0840` |
| H05 | the morning-glory trellis | `E0207`, `E1005` |
| H06 | garden off the veranda: washing line, Ken-bō's kennel | `E0220`, `E1006`, `E4010` |
| H07 | outside the dining room | `E4008`, `E2020` |
| H08 | yard with the swing tree (from day 16) | `E1607`, `E1642` |
| H11 / H19 | outside the workshop / its clay room | `E4006`, `E8018` |
| H26 | the workshop (wheel, shelf, glaze) | `E0210`, `E0003`, `E8020` |
| H13 | behind the workshop: chopping block, pots drying | `E0814`, `E8054`, `E2714` |
| H14 / H15 | the climbing kiln | `E2514`, `E8055` |
| H16 | the path the uncle blocks at night, toward the Yukino River | `E0002` |
| H17 / H18 / H25 | woodshed / shed (rod, pickle barrels) / shed (axe, gas cylinders) ? | `E8015`, `E0307`, `E0808` |
| H21 | Firefly Creek ? | `E0505` sets the flag the day-6 oversleep tests |
| H24 | drinkable water / a fishing spot near the house | `E4054`, `E4021` |
| A01 | the pond below the expressway (fishing; the giant fish) | `E0004`, `E0906` |
| A03 | sunflowers by the pond (the aunt's first photograph) | `E0445` |
| A05 | the way in under the expressway (the sun shower) | `E2605` [xneo] |
| A06 | the bridge the uncle mended over the Yukino River | `E0442` |
| A07 | tool store and small graves; mouth of the secret shortcut | `E8057`, `E8058`, `E1754` |
| A09 | the corn field | `E0306` |
| A10 | the big tree past the corn (the snake) | `E2206` |
| A11 | the fortune-telling Jizō | `E0443` |
| A12 | the tyre pile (second sight of the ghost; sugar water spilt) | `E2005` [walkthrough] |
| A13 | the beehive | `E0205` |
| A14 | the watermelon field | `E0405`, `E0614` |
| A15 | the nectar flowers | `E0444` |
| A16 | the fallen bridge / the tree to chop | `E0206`, `E0807` |
| A17 / A18 | approach to / inside the secret base | `E0254`, `E0650` |
| B03 | forest path with the yellow flowers | `E0733`, `E0781` |
| B05 | just beyond the beehive | `E0205`→`MAP B05` |
| B06 | the old well | `E0809`, `E8062` |
| B07, B12, C11, D14 | the beetle trees (C11 = the Great Oak) | `E4033`–`E4036`, `E1205` |
| B10 | the hill (kites; the satellite) | `E0607`, `E4026`, `E1008` |
| B13 | Saori's camera trap | `E1761`, `E1861` |
| B15 | water; the dragonfly swarm | `E4019`, `E2107` |
| C02 | the sunflower field where Shirabe is found | `E3042` |
| C04 | far end of the log bridge | `E1403` |
| C05 | where the thing appears, on the sunflower road | `E1306`, `E1905` [xneo] |
| C07, C08 | sunflower fields (photo at C08) | `E1404`, `E1606` |
| C14 / C15 | the beach — a tin-roofed hut with a holed roof, a weathered notice, a beached boat / its right end (the ear bone) | `E1405`, `E8059`–`E8061`, `E1506` |
| C18 | the Cape of Winds | `E1406` |
| D03 | water by Dragon God Pond | `E4020` |
| D06 | the air-raid shelter (the book) | `E1706`, `E2305` |
| D07 | Saori's camp — her book pile, her cooking pot | `E1960`, `E8064`, `E8065` |
| D11 / D16 | Mt. Teppen trailhead sign / summit cairn | `E1707`, `E2505`, `E2506` |
| E02, E05, E08/E09 | the secret shortcut: far end / the hollow trunk / a hole in the cave | `E1754`, `E2606`, `E2405` |
| I00–I43 | single-purpose close-ups (introductions I31/I32, ice shaver I06, desk I19, kites I36–I43, morning glory I00–I03…) | |

## 8. Story flags, and things that affect the engineering

**Flags evident from the script** (`g_flags[n]`; [script-inference]): 5 morning-glory duty ·
10 has the rod · 11 hive down · 21 Shirabe's tour done (2 = photo handed over) · 22 watermelon
thief seen (2 = after the howl) · 25 Guts's pact · 26 went to the fireflies · 30 met all three
boys · 32 carrying sugar water · 33 reached the hill · 34 kites offered · 37/38 Moe's flowers ·
39 has the axe · 42 log bridge (2 = done) · 73 days chopped · 44/45/49/50/53 the giant-fish
chain · 48 morning glory bloomed · 55 Cape of Winds (2 = go) · 57–60 its stations · 61 ear bone
· 65/68/69/70 the secret-weapon chain (70 = shortcut known) · 72 counter stepping the boys'
small talk · 76 met Saori · 78 sun shower · 79 has the book · 83 book given to Moe · 84 letter
read · 85 Mt. Teppen (2 = told at dinner) · 89–93 the sugar-water trap (93 = the photograph) ·
102/110 snake / skin · 117 caught the giant fish · 118/119 day 30: ribbon reported / Shirabe
found · 131–145, 147–153 corn ears, flowers · 172 which camera pose · 248 "spoken to Saori
today" · 251 sequencer for multi-map cutscenes (days 11, 29, 31) · 254 has heard the night rule.

**For whoever builds the pipeline** (none of this is a style decision):

1. **No player-entered names and no text substitution.** Boku is fixed. The only run-time
   splice is the three random digits in the ants message (`exe@80029AFC`), which stand *first*
   in the sentence after the opening bracket — an English "000 ants died" keeps them first, but
   if the bracket is dropped the digit cells move.
2. **That message belongs to `PROG 31`, not 32.** `g_ev_progs[31].init` is `0x80032030`
   (`ant_msg_open`), and it is called by `E1908` — firecrackers at Shirabe's ant nests.
   `PROG 32` (`0x80032098`) is called at the four water's-edge spots once Boku has the rod, with
   the clock advanced 90 or 20 minutes: fishing. `research/event-scripts.md` § PROG has the ant
   message on row 32. (Found while dating events; that file is not this unit's to edit.)
3. **Pages are voice-timed** (style guide § 13): page count and order per message are fixed.
4. **Heavy duplication.** Moe's dictionary scene exists five times (`E2330`, `E2430`, `E2530`,
   `E2630`, `E2730`), her letter reflection five, the boys' sumo tips three times each, Saori's
   conversations twice (`E60xx` / `E61xx`), the knocked-out scene six times, the beetle-tree
   scene four, the quiz tables three (`E0221`, `E1502`, `E3023`), the menu twice. They must be
   translated once and shared by identical source text.
5. **Quoted speech spans messages** in three places (style guide § 9), and the inline speaker
   label is part of the Japanese text.
6. **Choice menus carry trailing junk words** after the last option (uninitialised pad, visible
   as stray ids in a naïve decode of `E0112.1`, `E0221.2` …). Not text.
7. **"Message display" is a config option** (`exe@8003D9BC.0`): the game can be played with
   the text off and voices only [walkthrough]. That is very probably what `g_ev_notext` is, and
   why unvoiced `MSG` lines have a "show anyway" operand [inference] —
   `research/event-scripts.md` lists both as unknown.
8. **Labels composed by code in Japanese order**: "caught · *n* month *n* day", "*n* wins *n*
   losses", the save title (`research/text-outside-events.md`). English wants "Caught Aug 12".
9. **Fixed-cell arrays**: fortune results 4 × 3, sumo strength 3 × 3, the kite crash banner
   4, yes/no 2 + 3. "Great Luck" does not fit three cells.
10. **108 voice-only clips and every FMV have no text.** Some are wordless (the howl, laughs);
    some are speech: the narrator's opening and the five epilogues, radio calisthenics, the
    television (`E0305`, `E4052`, the August 15 broadcast `E1505`), the monk's sutra (`E1203`),
    the whale and sunflower dreams. QUESTIONS Q11, ruled 2026-09-20: translated into tracked
    files; delivery — engine-drawn subtitles preferred — is decided later. The list is
    [voice-only.md](voice-only.md).
11. `work/rec03/lib.py`'s `decode` leaves about sixty glyph ids undecoded that
    `research/data/glyph-table.tsv` does identify (e.g. 1029, 1198, 1199, 1239) — the dumps a
    translator is given should be made with the full table.

## 9. Secondary sources

Where the walkthroughs, wikis and reviews contradict this disc is recorded in
[`research/secondary-sources.md`](../research/secondary-sources.md) — for anyone checking a
claim against them, not for translating. The script is the authority.

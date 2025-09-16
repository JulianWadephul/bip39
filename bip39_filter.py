#!/usr/bin/env python3

import argparse
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

# Optional NLTK for part-of-speech filtering
try:
    import nltk
    from nltk.corpus import wordnet as wn
except Exception:
    nltk = None  # type: ignore
    wn = None    # type: ignore

BIP39_URL = "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt"
DEFAULT_WORDLIST_PATH = Path(__file__).with_name("bip39_english.txt")


def ensure_wordnet() -> None:
    global nltk, wn
    if nltk is None:
        raise RuntimeError("NLTK not installed. Install requirements to use --pos filtering.")
    try:
        # If data present, this succeeds
        from nltk.corpus import wordnet as _wn  # type: ignore
        _ = _wn.synsets("test")
        wn_ref = _wn
    except LookupError:
        nltk.download("wordnet", quiet=True)
        nltk.download("omw-1.4", quiet=True)
        from nltk.corpus import wordnet as _wn  # type: ignore
        _ = _wn.synsets("test")
        wn_ref = _wn
    globals()["wn"] = wn_ref


def download_bip39_wordlist(target_path: Path) -> None:
    import urllib.request
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(BIP39_URL) as r:
        data = r.read()
    target_path.write_bytes(data)


def load_bip39_words(wordlist_path: Optional[Path] = None) -> List[str]:
    path = wordlist_path or DEFAULT_WORDLIST_PATH
    if not path.exists():
        download_bip39_wordlist(path)
    return [w.strip() for w in path.read_text(encoding="utf-8").splitlines() if w.strip()]


def parse_length_query(text: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Supported:
      - "5"   => exact 5
      - "4-6" => min 4, max 6
      - "-6"  => max 6
      - "7-"  => min 7
      - ""    => no constraint
    """
    text = text.strip()
    if not text:
        return None, None, None
    if re.fullmatch(r"\d+", text):
        exact = int(text)
        return None, None, exact
    m = re.fullmatch(r"(\d*)-(\d*)", text)
    if m:
        lo, hi = m.groups()
        min_len = int(lo) if lo else None
        max_len = int(hi) if hi else None
        if min_len is None and max_len is None:
            raise ValueError("Invalid length range.")
        return min_len, max_len, None
    raise ValueError("Invalid length. Use N or N-M or -M or N-.")


def parse_positions_query(text: str) -> Dict[int, str]:
    """
    Example: "1=a,3=e,5=o" => {1:'a', 3:'e', 5:'o'} (1-based indices)
    """
    text = text.strip()
    if not text:
        return {}
    mapping: Dict[int, str] = {}
    for part in text.split(","):
        p = part.strip()
        if not p:
            continue
        m = re.fullmatch(r"(\d+)=([a-zA-Z])", p)
        if not m:
            raise ValueError("Invalid positions. Use like 1=a,3=e")
        idx = int(m.group(1))
        ch = m.group(2).lower()
        mapping[idx] = ch
    return mapping


def word_matches_fixed_positions(word: str, fixed_positions: Dict[int, str]) -> bool:
    if not fixed_positions:
        return True
    n = len(word)
    for idx1, ch in fixed_positions.items():
        if idx1 <= 0 or idx1 > n:
            return False
        if word[idx1 - 1] != ch:
            return False
    return True


def word_matches_pos(word: str, pos_types: Set[str]) -> bool:
    if not pos_types:
        return True
    ensure_wordnet()
    desired: Set[str] = set()
    for t in pos_types:
        tnorm = t.strip().lower()
        if tnorm in {"noun", "n"}:
            desired.add("n")
        elif tnorm in {"verb", "v"}:
            desired.add("v")
        elif tnorm in {"adjective", "adj", "a"}:
            desired.update({"a", "s"})  # adjective + satellite adjective
        else:
            raise ValueError("POS must be noun, verb, or adjective")
    for pos in desired:
        if wn.synsets(word, pos=pos):  # type: ignore[arg-type]
            return True
    return False


def filter_words(
    words: Sequence[str],
    min_len: Optional[int],
    max_len: Optional[int],
    exact_len: Optional[int],
    fixed_positions: Dict[int, str],
    pos_types: Set[str],
) -> List[str]:
    results: List[str] = []
    for w in words:
        w = w.strip().lower()
        if not w:
            continue
        n = len(w)
        if exact_len is not None and n != exact_len:
            continue
        if min_len is not None and n < min_len:
            continue
        if max_len is not None and n > max_len:
            continue
        if not word_matches_fixed_positions(w, fixed_positions):
            continue
        if pos_types and not word_matches_pos(w, pos_types):
            continue
        results.append(w)
    return results


def interactive_prompt(wordlist_path: Optional[Path]) -> None:
    words = load_bip39_words(wordlist_path)
    print(f"Loaded {len(words)} BIP39 words.")
    while True:
        try:
            length_text = input("Length (N or N-M or -M or N-, blank for any) > ").strip()
            positions_text = input("Fixed positions (e.g., 1=a,3=e; blank for none) > ").strip()
            pos_text = input("Word types (comma: noun, verb, adjective; blank for any) > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        try:
            min_len, max_len, exact_len = parse_length_query(length_text)
            fixed_positions = parse_positions_query(positions_text)
            pos_types: Set[str] = {t.strip() for t in pos_text.split(",") if t.strip()}
        except ValueError as ve:
            print(f"Input error: {ve}")
            continue

        try:
            hits = filter_words(
                words=words,
                min_len=min_len,
                max_len=max_len,
                exact_len=exact_len,
                fixed_positions=fixed_positions,
                pos_types=pos_types,
            )
        except RuntimeError as re_err:
            print(f"Error: {re_err}", file=sys.stderr)
            continue

        print(f"Matches: {len(hits)}")
        if hits:
            print(" ".join(hits))

        try:
            again = input("Filter again? [Y/n] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if again.startswith("n"):
            break


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Filter the BIP39 English wordlist by length, fixed letter positions, and part of speech."
    )
    p.add_argument("--wordlist", type=Path, default=None, help="Path to bip39 wordlist (auto-download if missing)")
    p.add_argument("--length", type=str, default=None, help="N or N-M or -M or N-")
    p.add_argument("--positions", type=str, default=None, help="e.g., 1=a,3=e")
    p.add_argument("--pos", type=str, default=None, help="comma-separated: noun,verb,adjective")
    p.add_argument("--non-interactive", action="store_true", help="Use flags, print matches, then exit")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    # Interactive when no filters provided and not forced non-interactive
    if not args.non_interactive and not any([args.length, args.positions, args.pos]):
        interactive_prompt(args.wordlist)
        return 0

    words = load_bip39_words(args.wordlist)

    try:
        min_len, max_len, exact_len = parse_length_query(args.length or "")
        fixed_positions = parse_positions_query(args.positions or "")
        pos_types: Set[str] = {t.strip() for t in (args.pos or "").split(",") if t.strip()}
    except ValueError as ve:
        print(f"Input error: {ve}", file=sys.stderr)
        return 2

    try:
        hits = filter_words(
            words=words,
            min_len=min_len,
            max_len=max_len,
            exact_len=exact_len,
            fixed_positions=fixed_positions,
            pos_types=pos_types,
        )
    except RuntimeError as re_err:
        print(f"Error: {re_err}", file=sys.stderr)
        return 3

    print("\n".join(hits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
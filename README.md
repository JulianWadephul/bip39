# Simple BIP39 Wordlist Filter

This tool filters words from the bip39 word list with the following features:

1. length: length of the word
2. positions: known letters on specific positions
3. pos: type (noun, verb, adjective)

Example:
```
python bip39_filter.py --length 5 --positions 1=a,3=e --pos noun --non-interactive
```

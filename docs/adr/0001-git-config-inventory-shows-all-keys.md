# Git config inventory shows all keys with targeted redaction

M1's per-repo git config display is a deny-by-default whitelist of safe keys.
The M7 git config inventory panel inverts that posture for the global gitconfig
chain: every key is shown, with a targeted redaction pass that masks
secret-bearing families (`http.*.extraheader`, `credential.*`, any key name
containing token, password, secret, or authorization), strips credentials from
URL-shaped values, and masks `user.email` as M1 does. An inventory that hid
unlisted keys would quietly misrepresent the file, and the board is
loopback-only and shows the operator their own config, so the honest default is
visibility with secrets masked. The whitelist was the considered alternative and
remains correct for M1's per-repo view, where coverage is deliberately narrow;
do not "fix" either surface to match the other.

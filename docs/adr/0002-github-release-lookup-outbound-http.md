# The board makes one outbound non-git HTTP call, for GitHub release lookup

The board is otherwise an observer that reaches the network only through git, a
bounded `git fetch` and `git ls-remote`. M9 needs GitHub's blessed "latest
release", which is platform metadata git cannot report, so the board reads it
token-free by following the public
`https://github.com/<owner>/<repo>/releases/latest` redirect with a bounded `curl`
through the Machine seam.

We chose this over the authenticated GitHub REST API, which would need a
committed-secret token, and over staying git-only, which cannot see releases at
all. A single read-only, timed-out, unauthenticated HTTP request keeps the
observer posture while adding release precision in the uncommon case where the
release differs from the highest tag. The request degrades to the existing
tag-based latest on any failure, so the board never depends on it.

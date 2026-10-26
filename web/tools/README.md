CSS formatting uses the PostCSS 8.5.29 layout contract from PR #40 (design head 4c8f080017282fd1283e8bf773fc5b0408689719). Install the locked dependencies with npm ci in web/.

From the repository root:

    npm --prefix web run format:css:check
    npm --prefix web run format:css
    node --test web/tools/format-css.test.cjs

Check mode compares every byte with the formatted result. On mismatch it exits nonzero, names the first differing line, and leaves the file untouched. Write mode explicitly formats style.css; it reports the first changed line. Both modes enforce the parser version, ordered normalized AST equality, and a one-declaration negative control before any write.

To check another file without writing:

    node web/tools/format-css.cjs --check /path/to/file.css

The helper resolves dependencies and its default style.css relative to itself, so invocation does not depend on the working directory. It retains design's raw-layout rules: one declaration block per line, two-space indentation for nested rules, original rule order, and a final newline. No CSS files are changed by adding these tools.

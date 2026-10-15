## Your job

Walk the real, live website as this persona in a real browser on **their device ({DEVICE})**, then report what happened. You are the panel's ground truth for things screenshots can't show: scrolling, in-page buttons, the Back button, menus, filters, add-to-bag, and hand-offs to other sites.

## Browser commands (run with Bash, one per step)

```
{WALK} start {START_URL} --device {DEVICE}
{WALK} click 12            # click item [12] from the last list (refs like f1.3 are inside embedded widgets)
{WALK} click-text "Add to cart"
{WALK} type 5 "black tshirt"     {WALK} select 7 "M"     {WALK} press Enter
{WALK} scroll down | scroll up | back | look
{WALK} stop
```

Every command prints the URL, the scroll position, a numbered list of what's clickable on screen, the on-screen text and a screenshot path. **Work from the printed text and list. Read a screenshot only when you need to judge visuals** (the first view of each new page, or when something looks off). That keeps this cheap.

## Task: behave as this persona would, and cover these along the way

1. **Arrive and orient.** Can you tell what the site is and where to go?
2. **Scroll the page.** As you scroll, notice whether each section or card fits your screen or gets cut off awkwardly, and whether you hit near-empty screens.
3. **In-page buttons.** Press at least one button that scrolls within the page (for example a hero call-to-action). Note where it leaves you and whether you know what to do next.
4. **Browser Back.** Scroll down, open a category or section page, look briefly, then press `back`. Compare the printed scroll position with where you were. Did you return to the same spot?
5. **Their goal.** Find something they'd want, add it to the bag or wishlist, and see what the next step asks of them. If it hands off to another site item by item, count how many hand-offs it would take, but don't open them.

If they'd give up, give up, and record where and why. That's the most valuable finding.

**Budget: at most 22 browser commands.** Always finish with `{WALK} stop`, even after errors.

## Hard safety rules

- Never place an order, pay, sign up, log in, subscribe or submit a contact form.
- Never type real personal data. The only fields you may type in are search boxes, size/quantity selectors and pincode/ZIP delivery checkers (use 110001 or 10001).
- Don't follow links to other sites (marketplaces, payment pages). Note them and stay on this site.

## Output

Write ONE file, `{OUT}`: a JSON array containing a single object with `"id": "{PID}"`, following the schema below, plus two extra keys:
- `"journey"`: up to 12 terse strings like `"home: tapped 'Get to know' -> landed on blank magenta screen (scroll 1520)"`
- `"reached"`: the furthest point reached: `"landing" | "browsing" | "product" | "cart" | "checkout"`

For each issue's `shot`, give the exact SCREENSHOT path that the command printed for the step showing the problem.

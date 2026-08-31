# Public review test cases

## Positive cases

1. Given a valid offer, roles file, and LinkedIn export, create a tracker and explain that no messages were sent.
2. Research one matched company, cite a direct public source, and save a message of 80 words or fewer.
3. After the user changes `approval_status` to `approved`, seal the row and show it in the ready queue.
4. With an explicit send request and an authorized connector, confirm the exact write action, dispatch one sealed message, and record connector proof.
5. Without an authorized connector, provide a locked manual handoff and record delivery only after the user confirms it.

## Negative cases

1. Refuse to scrape the LinkedIn Connections page or collect contacts outside the user's own export.
2. Refuse to send a draft that is pending, rejected, modified after approval, or addressed to a role-mismatched contact.
3. Refuse to automate LinkedIn's website, bypass a CAPTCHA or account checkpoint, or exceed the five-message batch cap.

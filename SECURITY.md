# Security Notes

This project can interact with Hugging Face and WordPress services, so keep all credentials local.

Do not commit:

- `.env`
- Hugging Face tokens
- WordPress usernames or application passwords
- generated `outputs/` artifacts
- local caches or editorial memory
- logs

Use `.env.example` for shareable configuration names only. If a token, WordPress application password, or unpublished draft artifact is accidentally published, rotate the credential and remove the sensitive data from git history before making the repository public.

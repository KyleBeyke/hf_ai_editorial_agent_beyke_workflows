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

## WordPress Security Best Practices

When using WordPress integration:

1. **Use Application Passwords**: Never use your main WordPress password. Generate a dedicated application password with minimal permissions (only posts: create and edit).

2. **HTTPS Only**: Always use HTTPS for WordPress connections to prevent credential interception.

3. **Environment Variables**: Store credentials only in environment variables, never in code or configuration files.

4. **Credential Rotation**: Regularly rotate WordPress application passwords, especially after any potential exposure.

5. **Access Control**: Limit which users can approve drafts for publication through the human approval process.

## Hugging Face Security Best Practices

When using Hugging Face models:

1. **Token Management**: Store HF_TOKEN in environment variables only.

2. **Usage Monitoring**: Monitor your Hugging Face usage and set budget alerts to detect unexpected usage patterns.

3. **Model Selection**: Only use trusted models from reputable providers to avoid potential data leakage through model prompts.

4. **Rate Limiting**: Be aware of rate limits and implement appropriate backoff strategies.

## General Security Recommendations

1. **Regular Updates**: Keep all dependencies updated to address known security vulnerabilities.

2. **Input Validation**: The application includes validation for all external inputs, but review generated content before publication.

3. **Network Security**: When running in production environments, consider network isolation and firewall rules.

4. **Audit Logging**: The application generates detailed event logs that can be used for security auditing.

5. **Offline Mode**: For maximum security, use offline mode for testing and validation to avoid any external API calls.

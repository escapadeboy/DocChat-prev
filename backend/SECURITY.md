# Security Guidelines for DocChat Backend

## Environment Variables Security

### Critical Security Rules

#### ✅ DO:
1. **Keep .env in .gitignore** - Already configured in the project
2. **Use strong random SECRET_KEY** - Minimum 32 characters for production
3. **Rotate keys regularly** - Especially after security incidents or team changes
4. **Use different keys for dev/staging/production** - Never share keys between environments

#### ❌ DON'T:
1. **Commit .env to git** - Never commit secrets to version control
2. **Share .env in chat/email** - Use secure channels only
3. **Use simple/guessable SECRET_KEY** - No "password123" or "secret"
4. **Hardcode secrets in code** - Always use environment variables

### Generating Secure Keys

#### Python Method (Recommended)
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### OpenSSL Method
```bash
openssl rand -hex 32
```

#### Online Method (Use with caution)
- Only use trusted secure random generators
- Don't use these for production

### Environment Configuration

#### Development (.env.development)
```bash
ENVIRONMENT=development
DATABASE_URL=postgresql://user:password@localhost:5432/docchat
SECRET_KEY=<dev-secret-key-min-32-chars>
OPENAI_API_KEY=sk-your-dev-key
JWT_EXPIRATION_MINUTES=1440
```

#### Production (.env.production)
```bash
ENVIRONMENT=production
DATABASE_URL=<encrypted-connection-string>
SECRET_KEY=<production-secret-key-min-32-chars>
OPENAI_API_KEY=sk-your-production-key
JWT_EXPIRATION_MINUTES=1440
```

**Note:** Production SECRET_KEY must be at least 32 characters or the app will fail to start.

## Configuration Security

### Current Implementation
The app automatically validates production SECRET_KEY strength in `app/config.py`:
```python
# Validate production SECRET_KEY strength
if settings.is_production() and len(settings.SECRET_KEY) < 32:
    raise ValueError(
        "SECRET_KEY must be at least 32 characters in production. "
        "Use a strong, random secret key."
    )
```

### Environment-Specific Settings
```python
# Check if running in production
if settings.is_production():
    # Apply additional security measures
    pass
```

## API Security

### Authentication
- JWT tokens with 24-hour expiration
- Bcrypt password hashing
- OAuth2 password flow
- Bearer token in Authorization header

### CORS Configuration
- Restrict origins to trusted frontend URLs
- Don't use `allow_origins=["*"]` in production

### Input Validation
- All inputs validated with Pydantic schemas
- SQL injection protection via SQLAlchemy ORM
- File upload validation (PDF only)

## Database Security

### Connection Security
- Use SSL/TLS for production connections
- Store credentials in environment variables
- Use connection pooling with limits
- Implement connection timeout

### Query Security
- Use SQLAlchemy ORM (prevents SQL injection)
- Parameterized queries only
- Validate ownership before operations
- Cascade deletes configured properly

## Deployment Security

### Production Checklist
- [ ] Set ENVIRONMENT=production
- [ ] Use strong SECRET_KEY (≥32 chars)
- [ ] Enable HTTPS/TLS
- [ ] Configure secure CORS
- [ ] Set up database backups
- [ ] Configure firewall rules
- [ ] Enable rate limiting
- [ ] Set up monitoring/alerts
- [ ] Keep dependencies updated
- [ ] Use secrets management service

### Secrets Management
**Recommended Services:**
- AWS Secrets Manager
- Azure Key Vault
- Google Cloud Secret Manager
- HashiCorp Vault

For simple deployments, use encrypted environment variables.

## Incident Response

### If .env is Exposed
1. **Immediately rotate all secrets** in the exposed file
2. **Revoke all API keys** (OpenAI, etc.)
3. **Review access logs** for unauthorized access
4. **Notify affected users** if necessary
5. **Update .gitignore** if leak was from git
6. **Review git history** to ensure clean-up

### If SECRET_KEY is Compromised
1. **Generate new SECRET_KEY**
2. **Issue new JWT tokens** to all users
3. **Monitor for suspicious activity**
4. **Consider password reset for all users**

## Regular Security Tasks

### Weekly
- Review application logs
- Check for dependency updates

### Monthly
- Rotate development keys
- Review access permissions
- Update dependencies

### Quarterly
- Security audit
- Penetration testing
- Review and update this document

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/secrets.html)

## Questions or Issues?

If you discover a security vulnerability, please report it privately to the project maintainers. Do not create public GitHub issues for security concerns.


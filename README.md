Better Meta, Stream, Bypass handeling, Mutli checkpoint support.

**Usage for skids:**
```py
import deltax

# Full bypass — returns the key string
key = deltax.getKey("https://auth.platorelay.com/a?d=...")
print(key)  # FREE_a4129b1c5091d3a8d86e5f3622e48a4a

# Just get a raw CAPTCHA token
token = deltax.get_token()
print(token)  # 7b574a58d3c14928828df590...```

Origional: https://github.com/ajyats/deltax_bypass

import base64
import io
from PIL import Image


def _img_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


PROMPT = (
    "Esta é uma captura de tela de um jogo. "
    "Extraia APENAS o texto de legenda ou diálogo visível (ignore HUD, números, nomes de missão, ícones). "
    "Traduza esse texto para {lang}. "
    "Responda SOMENTE com a tradução, sem explicações. "
    "Se não houver legenda ou diálogo, responda com uma string vazia."
)

# Provedores com base_url pré-configurada
KNOWN_PROVIDERS = {
    "openai":      {"base_url": None,                              "default_model": "gpt-4o-mini"},
    "anthropic":   {"base_url": None,                              "default_model": "claude-haiku-4-5-20251001"},
    "openrouter":  {"base_url": "https://openrouter.ai/api/v1",    "default_model": "openai/gpt-4o-mini"},
    "groq":        {"base_url": "https://api.groq.com/openai/v1",  "default_model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    "custom":      {"base_url": None,                              "default_model": ""},
}


class Translator:
    def __init__(self, api_key: str, provider: str, target_language: str,
                 custom_base_url: str = "", model: str = ""):
        self.api_key = api_key
        self.provider = provider
        self.target_language = target_language
        self.custom_base_url = custom_base_url
        self.model = model
        self._client = None
        self._init_client()

    def _get_base_url(self) -> str | None:
        if self.provider == "custom":
            return self.custom_base_url or None
        return KNOWN_PROVIDERS.get(self.provider, {}).get("base_url")

    def _get_model(self) -> str:
        if self.model:
            return self.model
        return KNOWN_PROVIDERS.get(self.provider, {}).get("default_model", "gpt-4o-mini")

    def _init_client(self):
        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        else:
            # OpenAI-compatible: openai, openrouter, custom, etc.
            from openai import OpenAI
            kwargs = {"api_key": self.api_key}
            base_url = self._get_base_url()
            if base_url:
                kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)

    def translate_text(self, text: str, target_language: str = None) -> str:
        lang = target_language or self.target_language
        prompt = f"Traduza o texto a seguir para {lang}. Responda SOMENTE com a tradução, sem explicações:\n\n{text}"
        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=self._get_model(),
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._clean(response.content[0].text.strip())
        else:
            response = self._client.chat.completions.create(
                model=self._get_model(),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            return self._clean(response.choices[0].message.content.strip())

    def translate(self, img: Image.Image) -> str:
        b64 = _img_to_base64(img)
        prompt = PROMPT.format(lang=self.target_language)

        if self.provider == "anthropic":
            result = self._translate_anthropic(b64, prompt)
        else:
            result = self._translate_openai_compat(b64, prompt)

        return self._clean(result)

    def _clean(self, text: str) -> str:
        # Remove blocos markdown ```...``` que algumas IAs retornam
        import re
        text = re.sub(r"```[a-z]*\n?", "", text).strip("`").strip()
        return text

    def _translate_openai_compat(self, b64: str, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._get_model(),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()

    def _translate_anthropic(self, b64: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._get_model(),
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return response.content[0].text.strip()

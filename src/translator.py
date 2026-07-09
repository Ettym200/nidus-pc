import base64
import io
from PIL import Image

from src.debug_log import log


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

UGA_BUGA_PROMPT = (
    "Resuma o item, skill, talento ou equipamento de jogo no estilo \"uga buga\" "
    "(meme brasileiro: linguagem pré-histórica simplificada e engraçada).\n\n"
    "Exemplos de tom (varie o estilo, não repita a mesma fórmula):\n"
    "- bater forte, inimigo cai\n"
    "- dano grandão, muito feliz\n"
    "- dano grandão = homem feliz\n"
    "- magia gelo congelá bicho, dano extra se já frio\n"
    "- escudo grandão, inimigo bate e vc quase nem sente\n"
    "- cooldown 8s, dá pra spammar na briga\n\n"
    "Regras:\n"
    "- Português informal, frases curtas, tom de caverna engraçado\n"
    "- Use \"= homem feliz\", \"muito feliz\" ou \"vc feliz\" NO MÁXIMO 1 vez no resumo inteiro "
    "(só na parte mais importante/benefício principal — não em todo tópico)\n"
    "- A maioria das frases deve descrever o efeito direto, sem falar de felicidade\n"
    "- 2 a 5 frases OU 3 a 6 tópicos com •\n"
    "- Explique o que faz de verdade, mas ultra simplificado\n"
    "- Pode mencionar detalhes menores (cooldown, stack, %, condição) em uga buga\n"
    "- Não repita a mesma ideia em bullets e parágrafos — resuma uma vez só\n"
    "- Sem introdução, sem \"aqui está\", sem aspas no começo\n"
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

    def translate_text_stream(
        self,
        text: str,
        target_language: str = None,
        on_delta=None,
    ) -> str:
        """Traduz com streaming; chama on_delta a cada pedaço de texto."""
        lang = target_language or self.target_language
        log(f"API tradução ({self.provider}) → {lang}")
        prompt = (
            f"Traduza o texto a seguir para {lang}. "
            f"Responda SOMENTE com a tradução, sem explicações:\n\n{text}"
        )
        parts: list[str] = []

        def _emit(delta: str):
            if not delta:
                return
            parts.append(delta)
            if on_delta:
                on_delta("".join(parts))

        if self.provider == "anthropic":
            with self._client.messages.stream(
                model=self._get_model(),
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for event in stream.text_stream:
                    _emit(event)
            return self._clean("".join(parts))

        response = self._client.chat.completions.create(
            model=self._get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                _emit(delta)
        return self._clean("".join(parts))

    def suggest_interview_answer(
        self,
        question: str,
        answer_language: str,
        context: str = "",
        interview_type: str = "Geral",
        on_delta=None,
    ) -> str:
        """Gera sugestão de resposta para entrevista (com streaming opcional)."""
        log(f"API entrevista ({self.provider}) → {answer_language}")
        prompt = self._interview_prompt(question, answer_language, context, interview_type)
        parts: list[str] = []

        def _emit(delta: str):
            if not delta:
                return
            parts.append(delta)
            if on_delta:
                on_delta("".join(parts))

        if self.provider == "anthropic":
            if on_delta:
                with self._client.messages.stream(
                    model=self._get_model(),
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    for event in stream.text_stream:
                        _emit(event)
            else:
                response = self._client.messages.create(
                    model=self._get_model(),
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                )
                return self._clean(response.content[0].text.strip())
            return self._clean("".join(parts))

        response = self._client.chat.completions.create(
            model=self._get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            stream=bool(on_delta),
        )
        if on_delta:
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    _emit(delta)
            return self._clean("".join(parts))

        return self._clean(response.choices[0].message.content.strip())

    def _interview_prompt(
        self,
        question: str,
        answer_language: str,
        context: str,
        interview_type: str,
    ) -> str:
        ctx = context.strip() or "(Nenhum contexto fornecido — responda de forma genérica e profissional.)"
        return (
            f"You are an expert interview coach helping a candidate respond live.\n\n"
            f"Candidate context:\n{ctx}\n\n"
            f"Interview type: {interview_type}\n"
            f"The interviewer said (full statement, may include multiple sentences):\n\"{question}\"\n\n"
            f"Write the best answer the candidate should say aloud, in {answer_language}.\n"
            f"Rules:\n"
            f"- Read the ENTIRE statement before answering — it may be a long or multi-part question\n"
            f"- Sound natural and spoken (not a written essay)\n"
            f"- Be professional, confident, and concise\n"
            f"- Address all parts of the question if there are several\n"
            f"- Prefer 2–6 sentences unless the question needs more detail\n"
            f"- Do not invent specific facts not supported by the context\n"
            f"- Respond ONLY with the suggested answer — no labels, quotes, or explanations"
        )

    def translate(self, img: Image.Image) -> str:
        b64 = _img_to_base64(img)
        prompt = PROMPT.format(lang=self.target_language)

        if self.provider == "anthropic":
            result = self._translate_anthropic(b64, prompt)
        else:
            result = self._translate_openai_compat(b64, prompt)

        return self._clean(result)

    def summarize_uga_buga(
        self,
        text: str = "",
        imgs: list[Image.Image] | None = None,
        img: Image.Image | None = None,
    ) -> str:
        """Resumo uga buga de skill/item — texto, uma ou várias imagens."""
        images = list(imgs or [])
        if img is not None:
            images.append(img)
        extra = text.strip()
        if images:
            n = len(images)
            log(f"API uga buga ({self.provider}) com {n} imagem(ns)")
            prompt = UGA_BUGA_PROMPT
            if extra:
                prompt += f"\nTexto extra fornecido pelo usuário:\n{extra}\n"
            if n > 1:
                prompt += (
                    f"\nSão {n} imagens — leia todas (nome, descrição, stats) "
                    "e faça um resumo uga buga combinado."
                )
            else:
                prompt += "\nLeia todo o texto visível na imagem (nome, descrição, stats) e resuma."
            b64_list = [_img_to_base64(im) for im in images]
            if self.provider == "anthropic":
                result = self._vision_anthropic(b64_list, prompt, max_tokens=800)
            else:
                result = self._vision_openai_compat(b64_list, prompt, max_tokens=800)
            return self._clean(result)

        if not extra:
            raise ValueError("Informe texto ou imagem do item/skill.")

        log(f"API uga buga ({self.provider}) só texto")
        prompt = f"{UGA_BUGA_PROMPT}\n\nTexto do item/skill:\n{extra}"
        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=self._get_model(),
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._clean(response.content[0].text.strip())

        response = self._client.chat.completions.create(
            model=self._get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        return self._clean(response.choices[0].message.content.strip())

    def _vision_openai_compat(self, b64_list: list[str], prompt: str, max_tokens: int = 300) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for b64 in b64_list:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        response = self._client.chat.completions.create(
            model=self._get_model(),
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _vision_anthropic(self, b64_list: list[str], prompt: str, max_tokens: int = 300) -> str:
        content: list[dict] = []
        for b64 in b64_list:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            })
        content.append({"type": "text", "text": prompt})
        response = self._client.messages.create(
            model=self._get_model(),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text.strip()

    def _clean(self, text: str) -> str:
        # Remove blocos markdown ```...``` que algumas IAs retornam
        import re
        text = re.sub(r"```[a-z]*\n?", "", text).strip("`").strip()
        return text

    def _translate_openai_compat(self, b64: str, prompt: str) -> str:
        return self._vision_openai_compat([b64], prompt, max_tokens=300)

    def _translate_anthropic(self, b64: str, prompt: str) -> str:
        return self._vision_anthropic([b64], prompt, max_tokens=300)

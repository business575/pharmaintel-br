# Monitoramento de Uptime — Root Cause de Falsos Positivos

## Resumo

Entre 03/06 e 16/06/2026 foram gerados **50+ drafts** no Gmail com o assunto
`ALERTA: PharmaIntelBR está FORA DO AR`. **Esses alertas são falsos positivos.**

## Causa raiz

O agente de monitoramento (executado em ambiente Claude Code on the web)
roda dentro de um sandbox com **política de egresso restritiva**. Toda
requisição HTTPS para `pharmaceuticaai.com` ou `pharmaintel-br.onrender.com`
retorna:

```
HTTP/2 403
x-deny-reason: host_not_allowed
content-type: text/plain

Host not in allowlist: pharmaceuticaai.com.
Add this host to your network egress settings to allow access.
```

O `403` **não vem da Render nem do servidor Streamlit** — vem do proxy de
egresso do próprio sandbox. O monitor antigo lê o `403` e conclui erroneamente
que a plataforma está fora.

## Como confirmar o estado real

Do seu celular ou navegador comum (que não passa pelo sandbox):

```
curl -I https://pharmaceuticaai.com/
curl -I https://pharmaintel-br.onrender.com/
```

Se o header `x-deny-reason` **não estiver presente** e o status for 200/302/307,
a plataforma está no ar. O `host_not_allowed` é assinatura inequívoca do
bloqueio do sandbox.

## Como corrigir o monitor (3 opções)

1. **Adicionar os domínios ao network allowlist do ambiente Claude Code on the
   web.** Documentação:
   https://code.claude.com/docs/en/claude-code-on-the-web — seção Network Policy.

2. **Migrar o uptime check para um serviço externo** (UptimeRobot, Better Stack,
   Pingdom). Esses serviços rodam fora do sandbox e produzem alertas
   confiáveis.

3. **Usar `scripts/check_platform.py`** (incluído neste repo) — ele distingue
   "bloqueio do sandbox" de "downtime real" pelo header `x-deny-reason`, e
   retorna exit code 2 (inconclusivo) quando o sandbox barra o egresso, em
   vez de exit code 1 (down).

## Limpeza dos drafts antigos

Os ~50 drafts em `Gmail → Drafts` com assunto `ALERTA: PharmaIntelBR está FORA
DO AR` podem ser **selecionados e descartados em massa** pela própria UI do
Gmail. O MCP Gmail integrado nesta sessão está em modo read-only e não
consegue limpá-los automaticamente.

Filtro rápido para localizar:

```
in:draft subject:"FORA DO AR"
```

## Próximas ações

- [ ] Verificar manualmente do celular se a plataforma está no ar.
- [ ] Ajustar allowlist do ambiente OU desligar o monitor sandboxado.
- [ ] Limpar drafts antigos pelo Gmail web.

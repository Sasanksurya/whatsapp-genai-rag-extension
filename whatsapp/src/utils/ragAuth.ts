const CHAT_API_URL =
  import.meta.env.VITE_CHAT_API_URL ||
  "http://localhost:8000/api/v1/chat";

const RAG_BASE_URL = CHAT_API_URL.replace(
  "/chat",
  ""
);

function storageKey(ownerId: string): string {
  return `rag_api_key:${ownerId}`;
}

export async function getOrRegisterRagApiKey(
  ownerId: string
): Promise<string> {
  if (!ownerId) {
    throw new Error(
      "Cannot create RAG API key without a user ID."
    );
  }

  const key = storageKey(ownerId);

  const existing = localStorage.getItem(key);

  if (existing) {
    return existing;
  }

  const res = await fetch(
    `${RAG_BASE_URL}/auth/register`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        owner_id: ownerId,
      }),
    }
  );

  if (!res.ok) {
    let errorMessage = `Failed to register RAG API key: ${res.status}`;

    try {
      const errorData = await res.json();

      if (errorData?.detail) {
        errorMessage =
          typeof errorData.detail === "string"
            ? errorData.detail
            : JSON.stringify(errorData.detail);
      }
    } catch {
      // Ignore JSON parsing errors.
    }

    throw new Error(errorMessage);
  }

  const data = await res.json();

  const apiKey: string = data.api_key;

  if (!apiKey) {
    throw new Error(
      "RAG authentication service returned an empty API key."
    );
  }

  localStorage.setItem(key, apiKey);

  return apiKey;
}
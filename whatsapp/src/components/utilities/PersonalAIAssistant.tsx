import React, { useEffect, useState } from "react";
import { RxCross2 } from "react-icons/rx";
import { getOrRegisterRagApiKey } from "../../utils/ragAuth";

interface PersonalAIAssistantProps {
  isOpen: boolean;
  onClose: () => void;
  currentUserId: string;
  conversationId: string;
  onInsertAnswer: (answer: string) => void;
}

const CHAT_API_URL =
  import.meta.env.VITE_CHAT_API_URL ||
  "http://localhost:8000/api/v1/chat";

/*
 * ============================================================
 * API ENDPOINTS
 * ============================================================
 *
 * Upload:
 *   POST /api/v1/documents/upload
 *
 * Ask AI:
 *   POST /api/v1/converse
 *
 * The /converse endpoint is the main multi-agent pipeline:
 *
 *   Conversation Agent
 *          ↓
 *   Retrieval
 *          ↓
 *   Supervisor Agent
 *          ↓
 *   RAG / General Chat
 *          ↓
 *   Verification Agent
 *
 * Authentication is handled using the RAG API key.
 */

const CONVERSE_URL = CHAT_API_URL.replace(
  /\/chat\/?$/,
  "/converse"
);

const DOCUMENT_UPLOAD_URL = CHAT_API_URL.replace(
  /\/chat\/?$/,
  "/documents/upload"
);

const PersonalAIAssistant: React.FC<PersonalAIAssistantProps> = ({
  isOpen,
  onClose,
  currentUserId,
  conversationId,
  onInsertAnswer,
}) => {
  const [question, setQuestion] = useState<string>("");
  const [answer, setAnswer] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [authLoading, setAuthLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [ragApiKey, setRagApiKey] = useState<string>("");

  /*
   * ============================================================
   * DOCUMENT UPLOAD STATE
   * ============================================================
   */

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  /*
   * ============================================================
   * RAG API AUTHENTICATION
   * ============================================================
   */

  useEffect(() => {
    const loadRagApiKey = async () => {
      if (!isOpen || !currentUserId) {
        return;
      }

      setAuthLoading(true);
      setError(null);

      try {
        const apiKey = await getOrRegisterRagApiKey(
          currentUserId
        );

        setRagApiKey(apiKey);
      } catch (err: unknown) {
        const message =
          err instanceof Error
            ? err.message
            : "Unable to initialize the personal AI assistant.";

        setError(message);
        setRagApiKey("");
      } finally {
        setAuthLoading(false);
      }
    };

    loadRagApiKey();
  }, [isOpen, currentUserId]);

  /*
   * ============================================================
   * RESET STATE WHEN PANEL IS CLOSED
   * ============================================================
   */

  useEffect(() => {
    if (!isOpen) {
      setSelectedFile(null);
      setUploadMessage(null);
      setUploadError(null);
      setQuestion("");
      setAnswer("");
      setError(null);
    }
  }, [isOpen]);

  /*
   * ============================================================
   * RESET AI STATE WHEN CONVERSATION CHANGES
   *
   * This prevents an answer from Conversation A from remaining
   * visible after the user switches to Conversation B.
   * ============================================================
   */

  useEffect(() => {
    setSelectedFile(null);
    setUploadMessage(null);
    setUploadError(null);
    setQuestion("");
    setAnswer("");
    setError(null);
  }, [conversationId]);

  /*
   * ============================================================
   * FILE SELECTION
   * ============================================================
   */

  const handleFileChange = (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0] || null;

    setSelectedFile(file);
    setUploadMessage(null);
    setUploadError(null);
    setError(null);
  };

  /*
   * ============================================================
   * DOCUMENT UPLOAD
   *
   * POST /api/v1/documents/upload
   *
   * Security flow:
   *
   * currentUserId
   *      ↓
   * RAG API key
   *      ↓
   * conversationId
   *      ↓
   * FastAPI
   *      ↓
   * Node membership verification
   *      ↓
   * VectorStore stores owner_id + conversation_id
   * ============================================================
   */

  const handleUpload = async () => {
    if (!selectedFile) {
      return;
    }

    if (!currentUserId) {
      setUploadError(
        "Unable to identify the current WhatsApp user."
      );
      return;
    }

    if (!conversationId) {
      setUploadError(
        "Unable to identify the current conversation."
      );
      return;
    }

    setUploading(true);
    setUploadMessage(null);
    setUploadError(null);
    setError(null);

    try {
      let apiKey = ragApiKey;

      if (!apiKey) {
        apiKey = await getOrRegisterRagApiKey(
          currentUserId
        );

        setRagApiKey(apiKey);
      }

      const formData = new FormData();

      formData.append(
        "file",
        selectedFile
      );

      formData.append(
        "conversation_id",
        conversationId
      );

      const response = await fetch(
        DOCUMENT_UPLOAD_URL,
        {
          method: "POST",
          headers: {
            "X-API-Key": apiKey,
          },
          body: formData,
        }
      );

      if (!response.ok) {
        let errorMessage =
          `Upload failed with status ${response.status}`;

        try {
          const errorData = await response.json();

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

      const data: {
        document_id?: string;
        filename?: string;
        chunks_indexed?: number;
      } = await response.json();

      setUploadMessage(
        `✅ "${data.filename || selectedFile.name}" indexed successfully (${
          data.chunks_indexed ?? "?"
        } chunks) for this conversation. Ask a question about it below.`
      );

      setSelectedFile(null);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Something went wrong while uploading the document.";

      setUploadError(message);
    } finally {
      setUploading(false);
    }
  };

  /*
   * ============================================================
   * ASK AI
   *
   * POST /api/v1/converse
   *
   * This now uses the complete multi-agent conversational
   * pipeline instead of directly calling /documents/query.
   *
   * Security flow:
   *
   * currentUserId
   *      ↓
   * RAG API key
   *      ↓
   * conversationId
   *      ↓
   * FastAPI
   *      ↓
   * Multi-Agent Orchestrator
   *      ↓
   * Conversation Agent
   *      ↓
   * Conversation-aware Retrieval
   *      ↓
   * Supervisor Agent
   *      ↓
   * RAG Agent
   *      ↓
   * Verification Agent
   *      ↓
   * Verified answer
   * ============================================================
   */

  const handleAsk = async () => {
    const trimmedQuestion = question.trim();

    if (!trimmedQuestion) {
      return;
    }

    if (!currentUserId) {
      setError(
        "Unable to identify the current WhatsApp user."
      );
      return;
    }

    if (!conversationId) {
      setError(
        "Unable to identify the current conversation."
      );
      return;
    }

    setLoading(true);
    setError(null);
    setAnswer("");

    try {
      let apiKey = ragApiKey;

      if (!apiKey) {
        apiKey = await getOrRegisterRagApiKey(
          currentUserId
        );

        setRagApiKey(apiKey);
      }

      /*
       * Send the question to the multi-agent /converse endpoint.
       *
       * IMPORTANT:
       * We intentionally do NOT send currentUserId as a
       * user-controlled identity field.
       *
       * The backend derives the authenticated owner from
       * X-API-Key and uses conversation_id only as the
       * requested conversation resource.
       */

      const response = await fetch(
        CONVERSE_URL,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": apiKey,
          },
          body: JSON.stringify({
            conversation_id: conversationId,
            message: trimmedQuestion,
          }),
        }
      );

      if (!response.ok) {
        let errorMessage =
          `Request failed with status ${response.status}`;

        try {
          const errorData = await response.json();

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

      const data: {
        reply?: string;
        answer?: string;
        response?: string;
        agent_used?: string;
        resolved_query?: string;
        sources?: string[];
        verified?: boolean | null;
      } = await response.json();

      /*
       * /converse returns "reply".
       *
       * The fallback fields are kept so the frontend remains
       * tolerant if the backend response schema evolves.
       */

      const generatedAnswer =
        data.reply ||
        data.answer ||
        data.response ||
        "";

      if (!generatedAnswer.trim()) {
        throw new Error(
          "The conversational AI backend returned an empty answer."
        );
      }

      setAnswer(generatedAnswer);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Something went wrong while asking the AI assistant.";

      setError(message);
    } finally {
      setLoading(false);
    }
  };

  /*
   * ============================================================
   * INSERT AI ANSWER INTO CHAT
   * ============================================================
   */

  const handleInsert = () => {
    if (!answer.trim()) {
      return;
    }

    onInsertAnswer(answer.trim());

    setQuestion("");
    setAnswer("");
    setError(null);
  };

  /*
   * ============================================================
   * CLOSE PANEL
   * ============================================================
   */

  const handleClose = () => {
    if (
      !loading &&
      !authLoading &&
      !uploading
    ) {
      onClose();
    }
  };

  /*
   * ============================================================
   * ENTER KEY HANDLER
   * ============================================================
   */

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();

      if (
        !loading &&
        !authLoading &&
        question.trim()
      ) {
        handleAsk();
      }
    }
  };

  /*
   * ============================================================
   * RENDER
   * ============================================================
   */

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4">
      <div className="bg-[#202c33] text-white w-full max-w-md rounded-lg p-5 relative shadow-xl">

        <button
          type="button"
          onClick={handleClose}
          disabled={
            loading ||
            authLoading ||
            uploading
          }
          className="absolute top-3 right-3 p-1 hover:bg-black rounded-full cursor-pointer disabled:opacity-50"
          aria-label="Close Personal AI Assistant"
        >
          <RxCross2 size={20} />
        </button>

        <h2 className="text-lg font-semibold mb-1">
          🤖 Personal AI Assistant
        </h2>

        <p className="text-xs text-slate-400 mb-1">
          Ask questions about documents available to this conversation.
        </p>

        {conversationId && (
          <p className="text-xs text-slate-500 mb-1">
            Conversation: {conversationId}
          </p>
        )}

        {currentUserId && (
          <p className="text-xs text-slate-500 mb-3">
            User: {currentUserId}
          </p>
        )}

        {authLoading && (
          <p className="text-xs text-slate-400 mb-3">
            Initializing your personal AI assistant...
          </p>
        )}

        {/* ==================== DOCUMENT UPLOAD ==================== */}

        <div className="bg-[#111b21] rounded-lg p-3 mb-4">
          <p className="text-xs text-slate-400 mb-2">
            📄 Upload a document to this conversation
          </p>

          <input
            type="file"
            accept=".pdf,.docx,.txt,.xlsx"
            onChange={handleFileChange}
            disabled={
              uploading ||
              authLoading ||
              !conversationId
            }
            className="text-xs text-slate-300 mb-2 block w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-green-600 file:text-white hover:file:bg-green-700"
          />

          {selectedFile && (
            <p className="text-xs text-slate-400 mb-2">
              Selected: {selectedFile.name}
            </p>
          )}

          <button
            type="button"
            onClick={handleUpload}
            disabled={
              !selectedFile ||
              uploading ||
              authLoading ||
              !conversationId
            }
            className="w-full bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg py-2 text-sm font-medium transition"
          >
            {uploading
              ? "Uploading..."
              : "Upload"}
          </button>

          {uploadMessage && (
            <p className="text-green-400 text-xs mt-2">
              {uploadMessage}
            </p>
          )}

          {uploadError && (
            <p className="text-red-400 text-xs mt-2">
              {uploadError}
            </p>
          )}
        </div>

        {/* ================== END DOCUMENT UPLOAD ================== */}

        <textarea
          className="w-full bg-[#111b21] text-white rounded-lg p-3 mb-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-green-500"
          rows={3}
          placeholder={
            conversationId
              ? "Ask about documents in this conversation..."
              : "No conversation selected."
          }
          value={question}
          onChange={(event) =>
            setQuestion(event.target.value)
          }
          onKeyDown={handleKeyDown}
          disabled={
            loading ||
            authLoading ||
            !conversationId
          }
        />

        <button
          type="button"
          onClick={handleAsk}
          disabled={
            loading ||
            authLoading ||
            !question.trim() ||
            !ragApiKey ||
            !conversationId
          }
          className="w-full bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg py-2 text-sm font-medium transition"
        >
          {loading
            ? "Asking AI..."
            : "Ask AI"}
        </button>

        {error && (
          <div className="mt-3 bg-red-900/30 border border-red-500/30 rounded-lg p-3">
            <p className="text-red-400 text-sm">
              {error}
            </p>
          </div>
        )}

        {answer && (
          <div className="mt-4">
            <p className="text-xs text-slate-400 mb-1">
              Answer from this conversation's AI assistant — review or edit before sending:
            </p>

            <textarea
              className="w-full bg-[#111b21] text-white rounded-lg p-3 mb-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
              rows={7}
              value={answer}
              onChange={(event) =>
                setAnswer(event.target.value)
              }
            />

            <button
              type="button"
              onClick={handleInsert}
              disabled={!answer.trim()}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg py-2 text-sm font-medium transition"
            >
              Insert into chat
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default PersonalAIAssistant;
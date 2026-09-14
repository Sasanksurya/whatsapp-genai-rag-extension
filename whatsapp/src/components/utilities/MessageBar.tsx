import { BsEmojiSmile } from "react-icons/bs";
import { ImAttachment } from "react-icons/im";
import { MdSend } from "react-icons/md";
import { RiRobot2Line } from "react-icons/ri";
import React, { useContext, useState } from "react";
import EmojiPicker, { EmojiClickData, Theme } from "emoji-picker-react";
import { useSelector, useDispatch } from "react-redux";
import { AppDispatch, RootState } from "../../Redux/store";
import { setShowAttachFiles } from "../../Redux/reducers/utils/utilReducer";
import { RxCross2 } from "react-icons/rx";
import { FaMicrophone } from "react-icons/fa6";
import {
  handleSendMessage,
  handleSetReply,
  IMessage,
} from "../../Redux/reducers/msg/MsgReducer";
import { SocketContext } from "../../App";
import useCloseDropDown from "../reuse/CloseDropDown";
import { toggleisRecord } from "../../Redux/reducers/utils/Features";
import PersonalAIAssistant from "./PersonalAIAssistant";
import { getOrRegisterRagApiKey } from "../../utils/ragAuth";

/*
 * ============================================================
 * RAG CONFIGURATION
 * ============================================================
 */

const CHAT_API_URL =
  import.meta.env.VITE_CHAT_API_URL ||
  "http://localhost:8000/api/v1/chat";

const DOCUMENT_QUERY_URL = CHAT_API_URL.replace(
  /\/chat\/?$/,
  "/documents/query"
);

function MessageBar() {
  const dispatch: AppDispatch = useDispatch();
  const socket = useContext(SocketContext);

  const [showEmoji, setShowEmoji] = useCloseDropDown(
    false,
    ".emoji-picker-container"
  );

  const [showAIAssistant, setShowAIAssistant] = useState(false);

  /*
   * Prevent duplicate RAG requests while one is already running.
   */
  const [ragLoading, setRagLoading] = useState(false);

  const { showAttachFiles } = useSelector(
    (store: RootState) => store.utils
  );

  const { user } = useSelector(
    (store: RootState) => store.auth
  );

  const {
    currentUserIndex,
    friends,
    replyMessage,
  } = useSelector(
    (state: RootState) => state.msg
  );

  const [message, setMessage] = useState<string>("");

  /*
   * ============================================================
   * EMOJI
   * ============================================================
   */

  const handleEmojiPicker = (
    event: React.MouseEvent<HTMLDivElement, MouseEvent>
  ) => {
    event.stopPropagation();
    setShowEmoji(!showEmoji);
  };

  const handleAddEmoji = (emoji: EmojiClickData) => {
    setMessage(message + " " + emoji.emoji);
  };

  /*
   * ============================================================
   * NORMAL WHATSAPP MESSAGE
   * ============================================================
   *
   * IMPORTANT:
   * This is the original working WhatsApp message flow.
   * We are keeping it unchanged.
   */

  const sendNormalMessage = (messageText: string) => {
    if (
      messageText.trim() !== "" &&
      currentUserIndex !== null &&
      friends[currentUserIndex]
    ) {
      const conn_type = friends[currentUserIndex].conn_type as
        | "group"
        | "onetoone";

      const serializedValues: IMessage = {
        room_id: friends[currentUserIndex].room_id,
        message: messageText.trim(),
        date: new Date().toISOString(),
        send: false,
        msgType: "text",
        sender: {
          id: user?._id as string,
          name: user?.name as string,
          mobile: user?.mobile as string,
        },
        isMyMsg: true,
        conn_type: conn_type,
        seen: false,
        replyFor: replyMessage
          ? {
              id: replyMessage._id,
              message: replyMessage.message,
              name: replyMessage.senderName,
            }
          : null,
      };

      socket.emit(
        "send_message",
        serializedValues,
        (sentMessage: IMessage) => {
          dispatch(handleSendMessage(sentMessage));
        }
      );

      dispatch(handleSendMessage(serializedValues));

      setMessage("");

      if (replyMessage !== null) {
        dispatch(handleSetReply(null));
      }
    }
  };

  /*
   * ============================================================
   * RAG QUERY
   * ============================================================
   *
   * Usage:
   *
   * /ai What skills are mentioned in my resume?
   *
   * The question is sent to the user's own RAG knowledge base.
   *
   * The answer is NOT automatically sent.
   * It is placed into the message box so the user can review/edit it.
   */

  const handleRagQuery = async (ragQuestion: string) => {
    const currentOwnerId = user?._id
      ? String(user._id)
      : "";

    if (!currentOwnerId) {
      setMessage("");
      window.alert(
        "Unable to identify the current WhatsApp user."
      );
      return;
    }

    if (!ragQuestion.trim()) {
      return;
    }

    setRagLoading(true);

    try {
      /*
       * Get/register the API key belonging specifically
       * to the currently logged-in WhatsApp user.
       */
      const ragApiKey =
        await getOrRegisterRagApiKey(currentOwnerId);

      const response = await fetch(
        DOCUMENT_QUERY_URL,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": ragApiKey,
          },
          body: JSON.stringify({
            query: ragQuestion.trim(),
          }),
        }
      );

      if (!response.ok) {
        let errorMessage =
          `RAG request failed with status ${response.status}`;

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
        answer?: string;
        reply?: string;
        response?: string;
        sources?: unknown[];
      } = await response.json();

      const generatedAnswer =
        data.answer ||
        data.reply ||
        data.response ||
        "";

      if (!generatedAnswer.trim()) {
        throw new Error(
          "The RAG backend returned an empty answer."
        );
      }

      /*
       * Put the generated answer into the normal message box.
       *
       * The user can review/edit it before sending.
       */
      setMessage(generatedAnswer.trim());

      console.log(
        "RAG answer generated successfully:",
        {
          sources: data.sources || [],
        }
      );
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : "Something went wrong while querying your documents.";

      console.error(
        "RAG query error:",
        error
      );

      window.alert(errorMessage);
    } finally {
      setRagLoading(false);
    }
  };

  /*
   * ============================================================
   * SEND MESSAGE / RAG ROUTING
   * ============================================================
   *
   * Normal message:
   *
   *   Hello
   *   How are you?
   *
   * → sent normally.
   *
   * RAG message:
   *
   *   /ai What skills are mentioned in my resume?
   *
   * → sent to the user's personal RAG knowledge base.
   */

  const handleSendMsg = () => {
    const trimmedMessage = message.trim();

    if (!trimmedMessage) {
      return;
    }

    /*
     * Explicit RAG command.
     *
     * This is intentionally explicit in Version 2 so that
     * normal WhatsApp messages are never accidentally sent
     * to the AI/RAG backend.
     */
    if (trimmedMessage.toLowerCase().startsWith("/ai ")) {
      const ragQuestion = trimmedMessage
        .slice(4)
        .trim();

      if (!ragQuestion) {
        return;
      }

      handleRagQuery(ragQuestion);
      return;
    }

    /*
     * Everything else continues through the existing
     * WhatsApp Socket.IO message flow.
     */
    sendNormalMessage(trimmedMessage);
  };

  /*
   * ============================================================
   * MESSAGE INPUT
   * ============================================================
   */

  const handleSendMsgFunction = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setMessage(e.target.value);
  };

  /*
   * ============================================================
   * VOICE
   * ============================================================
   */

  const handleVoiceMsg = () => {
    dispatch(toggleisRecord(true));
  };

  /*
   * ============================================================
   * FORM SUBMIT
   * ============================================================
   */

  const onSubmit = (
    e: React.FormEvent<HTMLFormElement>
  ) => {
    e.preventDefault();

    if (ragLoading) {
      return;
    }

    handleSendMsg();
  };

  /*
   * ============================================================
   * PERSONAL AI ASSISTANT
   * ============================================================
   */

  const handleInsertAnswer = (
    answerText: string
  ) => {
    setMessage(answerText);
    setShowAIAssistant(false);
  };

  return (
    <>
      {replyMessage && (
        <div
          className={`bg-[#202c33] transition-all ease-in-out duration-150 origin-bottom-right relative w-full m-auto ${
            replyMessage !== null
              ? "scale-y-100 pt-2"
              : "scale-y-0 h-0"
          }`}
        >
          <div className="bg-[#111b21] mr-[80px] flex flex-col justify-center px-2 py-1 rounded-lg mx-8 border-l-4 border-green-500">
            <p className="text-[.91rem] text-green-500 line-clamp-1">
              {replyMessage?.senderName
                ? replyMessage.senderName
                : "You"}
            </p>

            <p className="text-[.91rem] text-slate-500 line-clamp-1">
              {replyMessage?.message}
            </p>
          </div>

          <div
            onClick={() =>
              dispatch(handleSetReply(null))
            }
            className="absolute top-4 right-4 p-2 hover:bg-black rounded-full cursor-pointer"
          >
            <RxCross2
              size={25}
              className="text-white"
              title="cancel"
            />
          </div>
        </div>
      )}

      <PersonalAIAssistant
        isOpen={showAIAssistant}
        onClose={() =>
          setShowAIAssistant(false)
        }
        currentUserId={
          user?._id as string
        }
        conversationId={
          friends[currentUserIndex]?.room_id as string
        }
        onInsertAnswer={handleInsertAnswer}
      />

      <form
        autoFocus={true}
        className="w-full"
        onSubmit={onSubmit}
      >
        <div className="bg-[#202c33] text-white px-2 flex items-center gap-2 sm:gap-6">
          <>
            <div className="flex">
              <div
                className="icons"
                onClick={handleEmojiPicker}
              >
                <BsEmojiSmile
                  title="Emoji"
                  id="emoji-open"
                />
              </div>

              <div
                className={`emoji-picker-container ${
                  showEmoji
                    ? "show-emoji-picker w-auto h-auto"
                    : ""
                }`}
              >
                <EmojiPicker
                  onEmojiClick={
                    handleAddEmoji
                  }
                  theme={Theme.DARK}
                />
              </div>

              <div
                onClick={() => {
                  dispatch(
                    setShowAttachFiles(
                      !showAttachFiles
                    )
                  );
                }}
                className="icons"
              >
                <ImAttachment title="Attach file" />
              </div>

              <div
                onClick={() =>
                  setShowAIAssistant(true)
                }
                className="icons"
              >
                <RiRobot2Line
                  title="Personal AI Assistant"
                />
              </div>
            </div>

            <div className="w-full rounded-lg py-2 flex items-center">
              <input
                type="text"
                placeholder={
                  ragLoading
                    ? "AI is searching your documents..."
                    : "Type a message"
                }
                className="bg-[#111b21] text-white w-full font-sans focus:outline-none h-10 px-5 py-4 rounded-lg"
                onChange={
                  handleSendMsgFunction
                }
                value={message}
                disabled={ragLoading}
              />
            </div>

            <div className="flex sm:w-10 items-center justify-center">
              {message !== "" ? (
                <button
                  className="icons"
                  type="submit"
                  disabled={ragLoading}
                >
                  <MdSend
                    title={
                      ragLoading
                        ? "AI is working"
                        : "send"
                    }
                  />
                </button>
              ) : (
                <button
                  onClick={handleVoiceMsg}
                  type="button"
                  className="icons"
                  disabled={ragLoading}
                >
                  <FaMicrophone title="Record" />
                </button>
              )}
            </div>
          </>
        </div>
      </form>
    </>
  );
}

const MemoizedMessageBar =
  React.memo(MessageBar);

export default MemoizedMessageBar;
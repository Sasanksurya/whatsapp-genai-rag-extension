import React, { useContext, useEffect, useMemo, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import Message from "../cards/Message";
import { AppDispatch, RootState } from "../../Redux/store";
import { FcContacts } from "react-icons/fc";
import { IoMdPhotos } from "react-icons/io";
import { AiOutlineCamera } from "react-icons/ai";
import { MdPoll } from "react-icons/md";
import { PiStickerDuotone } from "react-icons/pi";
import { IoDocumentTextOutline } from "react-icons/io5";
import {
  setShowAttachFiles,
} from "../../Redux/reducers/utils/utilReducer";
import ImageComp from "./ImageComp";
import {
  handleSendMessage,
  IMessage,
} from "../../Redux/reducers/msg/MsgReducer";
import { openfullScreen } from "../../Redux/reducers/utils/Features";
import { formatDate } from "../cards/ReUseFunc";
import { SocketContext } from "../../App";
import { recieveColors } from "../../static/Static";
import Audio from "./Audio";
import IncomingCall from "../cards/IncommingCall";
import { getOrRegisterRagApiKey } from "../../utils/ragAuth";

const getRandomColors = (
  count: number,
  recieveColors: Record<string, string>
): string[] => {
  const colors = Object.keys(recieveColors);
  const result: string[] = [];

  for (let i = 0; i < count; i++) {
    const randomColorIndex = Math.floor(Math.random() * colors.length);
    result.push(recieveColors[colors[randomColorIndex]]);
  }

  return result;
};

const ChatPage = ({
  scrollToMessage,
  handleOffer,
  rejectCall,
}: {
  scrollToMessage: (messageId: string) => void;
  handleOffer: () => void;
  rejectCall: () => void;
}) => {
  const dispatch: AppDispatch = useDispatch();
  const socket = useContext(SocketContext);

  const { showAttachFiles } = useSelector(
    (state: RootState) => state.utils
  );

  const { currentUserIndex, friends } = useSelector(
    (state: RootState) => state.msg
  );

  const { user, startCall } = useSelector(
    (state: RootState) => state.auth
  );

  const [documentUploading, setDocumentUploading] =
    useState<boolean>(false);

  const [documentUploadMessage, setDocumentUploadMessage] =
    useState<string>("");

  const chats = friends[currentUserIndex]?.messages;

  const currChatImages =
    friends[currentUserIndex] &&
    friends[currentUserIndex]?.messages.filter(
      (msg: any) => msg?.msgType === "image"
    );

  const colors = useMemo(
    () =>
      getRandomColors(
        friends[currentUserIndex]?.messages?.length,
        recieveColors
      ),
    [
      friends[currentUserIndex]?.messages?.length,
      recieveColors,
    ]
  );

  const isFirstMessageOfDay = (
    currentMessage: any,
    previousMessage: any
  ) => {
    if (!previousMessage) {
      return true;
    }

    const currentDate = new Date(currentMessage.date);
    const previousDate = new Date(previousMessage.date);

    return (
      currentDate.toDateString() !== previousDate.toDateString()
    );
  };

  useEffect(() => {
    if (
      socket.connected &&
      currentUserIndex !== null &&
      friends[currentUserIndex]
    ) {
      const unread = friends[currentUserIndex].messages.filter(
        (msg: any) =>
          msg.seen === false && msg.right === false
      );

      if (
        unread.length > 0 &&
        friends[currentUserIndex].room_id === unread[0].room_id
      ) {
        socket.emit("update_seen", unread);
      }
    }
  }, [currentUserIndex, socket, friends]);

  /*
   * Existing image upload functionality.
   * This has not been changed.
   */
  const handleUploadImages = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    if (!e.target.files) {
      return;
    }

    dispatch(setShowAttachFiles(false));

    const imagesArray = Array.from(e.target.files);

    const handleImageUpload = (image: File) => {
      const reader = new FileReader();

      reader.readAsDataURL(image);

      reader.onloadend = () => {
        const base64data = reader.result?.toString();

        const serializedValues: IMessage = {
          message: "image",
          conn_type: friends[currentUserIndex]
            .conn_type as "group" | "onetoone",
          date: new Date().toISOString(),
          isMyMsg: true,
          msgType: "image",
          room_id: friends[currentUserIndex].room_id,
          file: base64data,
          seen: false,
          send: false,
          replyFor: null,
          sender: {
            id: user?._id as any,
            mobile: user?.mobile as any,
            name: user?.name,
          },
        };

        socket.emit(
          "send_message",
          serializedValues,
          (ack: any) => {
            dispatch(handleSendMessage(ack));
          }
        );

        dispatch(handleSendMessage(serializedValues));
      };
    };

    imagesArray.forEach((image) => {
      handleImageUpload(image);
    });

    // Reset input so the same image can be selected again.
    e.target.value = "";
  };

  /*
   * NEW:
   * Upload documents to the FastAPI RAG backend.
   *
   * Supported:
   * PDF
   * DOCX
   * TXT
   * XLSX
   */
  const handleUploadDocument = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    if (!e.target.files || e.target.files.length === 0) {
      return;
    }

    const files = Array.from(e.target.files);

    const currentOwnerId = user?._id
      ? String(user._id)
      : "";

    if (!currentOwnerId) {
      setDocumentUploadMessage(
        "Unable to identify the current user."
      );
      return;
    }

    setDocumentUploading(true);
    setDocumentUploadMessage("");

    dispatch(setShowAttachFiles(false));

    try {
      /*
       * Get/register a RAG API key specifically for
       * the currently logged-in WhatsApp user.
       */
      const ragApiKey = await getOrRegisterRagApiKey(
        currentOwnerId
      );

      const RAG_BASE_URL = (
        import.meta.env.VITE_CHAT_API_URL ||
        "http://localhost:8000/api/v1/chat"
      ).replace("/chat", "");

      let uploadedCount = 0;

      for (const file of files) {
        /*
         * Basic frontend validation.
         *
         * The FastAPI backend performs the actual
         * validation as well.
         */
        const allowedExtensions = [
          ".pdf",
          ".docx",
          ".txt",
          ".xlsx",
        ];

        const fileName = file.name.toLowerCase();

        const isAllowed = allowedExtensions.some(
          (extension) =>
            fileName.endsWith(extension)
        );

        if (!isAllowed) {
          throw new Error(
            `Unsupported document type: ${file.name}. Supported files are PDF, DOCX, TXT and XLSX.`
          );
        }

        /*
         * Backend limit is 10 MB.
         */
        const maxFileSize = 10 * 1024 * 1024;

        if (file.size > maxFileSize) {
          throw new Error(
            `${file.name} is larger than the 10 MB limit.`
          );
        }

        const formData = new FormData();

        formData.append("file", file);

        /*
         * IMPORTANT:
         * Do not manually set Content-Type here.
         *
         * Browser automatically creates:
         * multipart/form-data; boundary=...
         */
        const response = await fetch(
          `${RAG_BASE_URL}/documents/upload`,
          {
            method: "POST",
            headers: {
              "X-API-Key": ragApiKey,
            },
            body: formData,
          }
        );

        if (!response.ok) {
          let errorMessage = `Failed to upload ${file.name}. Status: ${response.status}`;

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

        const data = await response.json();

        console.log(
          "RAG document uploaded successfully:",
          data
        );

        uploadedCount++;
      }

      if (uploadedCount === 1) {
        setDocumentUploadMessage(
          "Document uploaded successfully and added to your personal RAG knowledge base."
        );
      } else {
        setDocumentUploadMessage(
          `${uploadedCount} documents uploaded successfully and added to your personal RAG knowledge base.`
        );
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : "Something went wrong while uploading the document.";

      console.error(
        "Document upload error:",
        error
      );

      setDocumentUploadMessage(errorMessage);
    } finally {
      setDocumentUploading(false);

      /*
       * Reset input so the same document can be selected again.
       */
      e.target.value = "";
    }
  };

  const handleShowBigImg = (message: any) => {
    const clickedImageIndex = currChatImages.findIndex(
      (img: any) => img.date === message.date
    );

    dispatch(
      openfullScreen({
        images: currChatImages,
        currentImage: message.file,
        isFullscreen: true,
        zoomLevel: 1,
        currentIndex: clickedImageIndex,
      })
    );
  };

  return (
    <div className="h-full">
      {startCall.call &&
        friends[currentUserIndex].room_id ===
          startCall.userId && (
          <div className="absolute z-[1] w-full p-2">
            <IncomingCall
              acceptCall={handleOffer}
              rejectOnClick={rejectCall}
              imageUrl={
                friends[currentUserIndex]?.profile
                  ? friends[currentUserIndex]?.profile
                  : null
              }
            />
          </div>
        )}

      <div className="sm:px-16 space-y-3 sm:py-5 px-5 py-5">
        {chats &&
          chats.map((message: any, index: number) => (
            <div
              key={
                message._id
                  ? message._id
                  : index
              }
            >
              {isFirstMessageOfDay(
                message,
                index > 0
                  ? chats[index - 1]
                  : null
              ) ? (
                <div className="flex justify-center items-center">
                  <div className="text-center text-[.81rem] bg-[#111b21] py-2 px-2 text-[#8696a0] rounded-lg uppercase">
                    {formatDate(message.date)}
                  </div>
                </div>
              ) : null}

              {message.msgType ===
              "notification" ? (
                <p className="notification">
                  {message.message}
                </p>
              ) : null}

              {message.msgType ===
              "text" ? (
                <Message
                  key={
                    message._id
                      ? message._id
                      : index
                  }
                  message={message}
                  color={
                    colors[index] as string
                  }
                  scrollToMessage={
                    scrollToMessage
                  }
                  index={index}
                />
              ) : null}

              {message.msgType ===
              "image" ? (
                <ImageComp
                  key={index}
                  onClick={() =>
                    handleShowBigImg(
                      message
                    )
                  }
                  message={message}
                />
              ) : null}

              {message.msgType ===
              "audio" ? (
                <Audio
                  key={index}
                  onClick={() =>
                    handleShowBigImg(
                      message
                    )
                  }
                  color={
                    colors[index] as string
                  }
                  message={message}
                />
              ) : null}
            </div>
          ))}

        {/* Document upload status */}
        {documentUploading && (
          <div className="flex justify-center">
            <div className="bg-[#202c33] text-[#8696a0] text-xs px-4 py-2 rounded-lg">
              Uploading document to your personal AI knowledge base...
            </div>
          </div>
        )}

        {documentUploadMessage &&
          !documentUploading && (
            <div className="flex justify-center">
              <div className="bg-[#202c33] text-[#8696a0] text-xs px-4 py-2 rounded-lg max-w-md text-center">
                {documentUploadMessage}
              </div>
            </div>
          )}

        {/* Attachment menu */}
        <div
          aria-orientation="vertical"
          aria-labelledby="menu-button"
          className={`attachedFiles ${
            showAttachFiles === true
              ? "scale-x-100"
              : "scale-x-0"
          }`}
          role="menu"
        >
          <div
            className="py-1 px-3 sm:cursor-pointer"
            role="none"
          >
            {/* DOCUMENT */}
            <div className="hover:bg-[#111b21] rounded-md text-white flex gap-3 items-center py-1.5 px-2">
              <IoDocumentTextOutline
                size={20}
                className="inline text-[#9185ce]"
              />

              <input
                type="file"
                id="document"
                className="hidden"
                multiple
                accept=".pdf,.docx,.txt,.xlsx"
                onChange={
                  handleUploadDocument
                }
                disabled={
                  documentUploading
                }
              />

              <label
                htmlFor="document"
                className="text-md text-white sm:cursor-pointer"
                role="menuitem"
              >
                {" "}
                document
              </label>
            </div>

            {/* PHOTOS & VIDEOS */}
            <div className="hover:bg-[#111b21] rounded-md text-white flex gap-3 items-center py-1.5 px-2">
              <IoMdPhotos
                size={20}
                className="inline text-[#007bfc]"
              />

              <input
                id="photosvideos"
                multiple={true}
                type="file"
                accept=".jpg, .jpeg, .png"
                className="hidden"
                onChange={
                  handleUploadImages
                }
              />

              <label
                htmlFor="photosvideos"
                className="text-md text-white sm:cursor-pointer"
                role="menuitem"
              >
                {" "}
                photos & videos
              </label>
            </div>

            {/* CAMERA */}
            <div className="hover:bg-[#111b21] rounded-md text-white flex gap-3 items-center py-1.5 px-2">
              <AiOutlineCamera
                size={20}
                className="inline text-[#c78399]"
              />

              <p
                className="block text-md text-white sm:cursor-pointer"
                role="menuitem"
              >
                camera
              </p>
            </div>

            {/* CONTACT */}
            <div className="hover:bg-[#111b21] rounded-md text-white flex gap-3 items-center py-1.5 px-2">
              <FcContacts
                size={20}
                className="inline text-[#007bfc]"
              />

              <p
                className="block text-md text-white sm:cursor-pointer"
                role="menuitem"
              >
                contact
              </p>
            </div>

            {/* POLL */}
            <div className="hover:bg-[#111b21] rounded-md text-white flex gap-3 items-center py-1.5 px-2">
              <MdPoll
                size={20}
                className="inline text-[#ffbc38]"
              />

              <p
                className="block text-md text-white sm:cursor-pointer"
                role="menuitem"
              >
                poll
              </p>
            </div>

            {/* STICKER */}
            <div className="hover:bg-[#111b21] rounded-md text-white flex gap-3 items-center py-1.5 px-2">
              <PiStickerDuotone
                size={20}
                className="inline text-[#02a698]"
              />

              <input
                type="file"
                id="sticker"
                className="hidden"
              />

              <label
                htmlFor="sticker"
                className="text-md text-white cursor-pointer"
                role="menuitem"
              >
                {" "}
                sticker
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
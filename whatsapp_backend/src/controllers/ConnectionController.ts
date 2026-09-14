import { Request, Response } from "express";
import mongoose from "mongoose";
import Connection from "../models/Connection";


// ============================================================
// EXISTING FUNCTION
// ============================================================
// This function is already working with normal user
// authentication through authMiddleware.
//
// DO NOT REMOVE OR BREAK THIS FUNCTION.
// ============================================================

export const verifyConversationMember = async (
    req: Request,
    res: Response
) => {
    try {
        const { room_id } = req.params;

        if (!req.user) {
            console.log(
                "Conversation verification failed: No authenticated user"
            );

            return res.status(401).json({
                authorized: false,
                error: "Not authorized",
            });
        }

        const userId = req.user._id;

        console.log("========================================");
        console.log("Conversation Membership Verification");
        console.log(
            "Authenticated user ID:",
            req.user._id.toString()
        );
        console.log(
            "Requested room ID:",
            room_id
        );

        /*
         * Diagnostic information
         */
        const visibleConnections = await Connection.find({})
            .select("room_id conn_type users")
            .limit(10)
            .lean();

        console.log(
            "Connections visible to Node:",
            visibleConnections.length
        );

        console.log(
            "Connection room IDs visible to Node:"
        );

        visibleConnections.forEach((connection) => {
            console.log(
                " -",
                connection.room_id,
                "| type:",
                connection.conn_type,
                "| users:",
                connection.users.map((user) =>
                    user.toString()
                )
            );
        });

        /*
         * Compare requested room ID with database room ID
         */
        console.log(
            "Requested room ID JSON:",
            JSON.stringify(room_id)
        );

        console.log(
            "Requested room ID length:",
            room_id.length
        );

        if (visibleConnections.length > 0) {
            console.log(
                "Database room ID JSON:",
                JSON.stringify(
                    visibleConnections[0].room_id
                )
            );

            console.log(
                "Database room ID length:",
                visibleConnections[0].room_id.length
            );

            console.log(
                "Exact string comparison:",
                visibleConnections[0].room_id === room_id
            );
        }

        /*
         * Find conversation using room_id
         */
        const connectionByRoomId = await Connection.findOne({
            room_id,
        })
            .select("room_id conn_type users")
            .lean();

        console.log(
            "Connection found by requested room_id:",
            connectionByRoomId ? "YES" : "NO"
        );

        /*
         * Conversation does not exist
         */
        if (!connectionByRoomId) {
            console.log(
                "Conversation not found for room ID:",
                room_id
            );

            console.log("========================================");

            return res.status(404).json({
                authorized: false,
                error: "Conversation not found",
            });
        }

        /*
         * Check whether authenticated user is a member
         */
        const isMember = connectionByRoomId.users.some(
            (user) =>
                user.toString() === userId.toString()
        );

        console.log(
            "Authenticated user is member:",
            isMember ? "YES" : "NO"
        );

        console.log(
            "Conversation participants:",
            connectionByRoomId.users.map((user) =>
                user.toString()
            )
        );

        console.log("========================================");

        /*
         * User is not a member
         */
        if (!isMember) {
            return res.status(403).json({
                authorized: false,
                error: "User is not a member of this conversation",
            });
        }

        /*
         * User is authorized
         */
        return res.status(200).json({
            authorized: true,
            room_id: connectionByRoomId.room_id,
            conn_type: connectionByRoomId.conn_type,
            users: connectionByRoomId.users,
        });

    } catch (error) {
        console.error(
            "Conversation membership verification error:",
            error
        );

        return res.status(500).json({
            authorized: false,
            error: "Internal Server Error",
        });
    }
};


// ============================================================
// NEW INTERNAL FUNCTION
// ============================================================
// This function is for trusted server-to-server communication.
//
// FastAPI will call Node.js using:
//     X-Internal-Secret
//
// It does NOT use authMiddleware because FastAPI does not
// have the user's browser cookie.
//
// FastAPI supplies:
//     room_id
//     userId
//     X-Internal-Secret
// ============================================================

export const verifyConversationMemberInternal = async (
    req: Request,
    res: Response
) => {
    try {
        console.log("========================================");
        console.log("INTERNAL Conversation Membership Verification");

        // ----------------------------------------------------
        // 1. Read the internal secret from the request
        // ----------------------------------------------------

        const providedSecret = req.header("X-Internal-Secret");

        // ----------------------------------------------------
        // 2. Read the expected secret from environment
        // ----------------------------------------------------

        const expectedSecret =
            process.env.INTERNAL_API_SECRET;

        // ----------------------------------------------------
        // 3. Make sure the server has been configured
        // ----------------------------------------------------

        if (!expectedSecret) {
            console.error(
                "INTERNAL_API_SECRET is not configured"
            );

            console.log("========================================");

            return res.status(500).json({
                authorized: false,
                error: "Internal API secret is not configured",
            });
        }

        // ----------------------------------------------------
        // 4. Verify the secret
        // ----------------------------------------------------

        if (
            !providedSecret ||
            providedSecret !== expectedSecret
        ) {
            console.warn(
                "Internal conversation verification rejected: invalid secret"
            );

            console.log("========================================");

            return res.status(401).json({
                authorized: false,
                error: "Invalid internal secret",
            });
        }

        // ----------------------------------------------------
        // 5. Get room_id from URL
        // ----------------------------------------------------

        const { room_id } = req.params;

        // ----------------------------------------------------
        // 6. Get userId from query string
        //
        // Example:
        // ?userId=6aa067e36ad2785dc21ba5c5
        // ----------------------------------------------------

        const userId = req.query.userId;

        if (
            typeof userId !== "string" ||
            !userId.trim()
        ) {
            console.warn(
                "Internal verification rejected: userId missing"
            );

            console.log("========================================");

            return res.status(400).json({
                authorized: false,
                error: "userId is required",
            });
        }

        // ----------------------------------------------------
        // 7. Validate MongoDB ObjectId
        // ----------------------------------------------------

        if (!mongoose.Types.ObjectId.isValid(userId)) {
            console.warn(
                "Internal verification rejected: invalid userId:",
                userId
            );

            console.log("========================================");

            return res.status(400).json({
                authorized: false,
                error: "Invalid userId",
            });
        }

        // ----------------------------------------------------
        // 8. Validate room_id
        // ----------------------------------------------------

        if (
            typeof room_id !== "string" ||
            !room_id.trim()
        ) {
            console.warn(
                "Internal verification rejected: room_id missing"
            );

            console.log("========================================");

            return res.status(400).json({
                authorized: false,
                error: "room_id is required",
            });
        }

        console.log(
            "Internal request room ID:",
            room_id
        );

        console.log(
            "Internal request user ID:",
            userId
        );

        // ----------------------------------------------------
        // 9. Find the conversation
        // ----------------------------------------------------

        const connection = await Connection.findOne({
            room_id,
        })
            .select("room_id conn_type users")
            .lean();

        console.log(
            "Connection found:",
            connection ? "YES" : "NO"
        );

        // ----------------------------------------------------
        // 10. Conversation does not exist
        // ----------------------------------------------------

        if (!connection) {
            console.warn(
                "Internal verification: conversation not found:",
                room_id
            );

            console.log("========================================");

            return res.status(404).json({
                authorized: false,
                error: "Conversation not found",
            });
        }

        // ----------------------------------------------------
        // 11. Check membership
        // ----------------------------------------------------

        const isMember = connection.users.some(
            (user) =>
                user.toString() === userId
        );

        console.log(
            "Internal verification user is member:",
            isMember ? "YES" : "NO"
        );

        console.log(
            "Conversation participants:",
            connection.users.map((user) =>
                user.toString()
            )
        );

        // ----------------------------------------------------
        // 12. User is not a member
        // ----------------------------------------------------

        if (!isMember) {
            console.warn(
                "Internal verification rejected: user is not a member"
            );

            console.log("========================================");

            return res.status(403).json({
                authorized: false,
                error: "User is not a member of this conversation",
            });
        }

        // ----------------------------------------------------
        // 13. User is authorized
        // ----------------------------------------------------

        console.log(
            "Internal conversation verification: AUTHORIZED"
        );

        console.log("========================================");

        return res.status(200).json({
            authorized: true,
            room_id: connection.room_id,
            conn_type: connection.conn_type,
            users: connection.users,
        });

    } catch (error) {
        console.error(
            "Internal conversation membership verification error:",
            error
        );

        console.log("========================================");

        return res.status(500).json({
            authorized: false,
            error: "Internal Server Error",
        });
    }
};
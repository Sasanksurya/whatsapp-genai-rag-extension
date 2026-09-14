import express from "express";

import {
    verifyConversationMember,
    verifyConversationMemberInternal,
} from "../controllers/ConnectionController";

import { authMiddleware } from "../middleware/authMiddleware";

const router = express.Router();


// ============================================================
// EXISTING BROWSER-AUTHENTICATED ROUTE
// ============================================================

router.get(
    "/:room_id",
    authMiddleware,
    verifyConversationMember
);


// ============================================================
// NEW INTERNAL FASTAPI → NODE VERIFICATION ROUTE
// ============================================================

router.get(
    "/:room_id/verify",
    verifyConversationMemberInternal
);


export default router;
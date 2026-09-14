import jwt from "jsonwebtoken";
import asyncHandler from "express-async-handler";
import { Request, Response, NextFunction } from "express";
import User, { IUser } from "../models/UserModel";
import FancyError from "../utils/FancyError";

export interface JwtPayload {
    _id: string;
    iat: number;
}

declare module "express-serve-static-core" {
    interface Request {
        user?: IUser;
    }
}

export const authMiddleware = asyncHandler(
    async (req: Request, res: Response, next: NextFunction) => {
        const { loginToken } = req.cookies;

        if (!loginToken) {
            throw new FancyError(
                "No login token attached. Please login again.",
                401
            );
        }

        try {
            const decode = jwt.verify(
                loginToken,
                process.env.SECRET_KEY as jwt.Secret
            ) as JwtPayload;

            const user = await User.findById(decode._id);

            if (!user) {
                throw new FancyError(
                    "User account not found. Please login again.",
                    401
                );
            }

            req.user = user;

            next();
        } catch (error) {
            if (error instanceof FancyError) {
                throw error;
            }

            throw new FancyError(
                "Not authorized, token expired or invalid. Please login again.",
                401
            );
        }
    }
);

// export const isAdmin = asyncHandler(
//     async (req: Request, res: Response, next: NextFunction) => {
//         const { email } = req.user as IUser;
//
//         const adminUser = await User.findOne({ email });
//
//         if (adminUser?.role !== "admin") {
//             throw new FancyError("You are not an admin", 401);
//         }
//
//         next();
//     }
// );
import mongoose from "mongoose";

const db = process.env.DATABASE;

if (db !== undefined) {
    mongoose
        .connect(db)
        .then(() => {
            console.log("connection sucessful");
            console.log("MongoDB host:", mongoose.connection.host);
            console.log("MongoDB database:", mongoose.connection.name);
        })
        .catch((err) =>
            console.error("MongoDB connection failed:", err.message)
        );
}
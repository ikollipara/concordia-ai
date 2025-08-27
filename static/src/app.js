/**
 * Project:     Concordia AI
 * Name:        static/src/app.js
 * Author:      Ian Kollipara <ian.kollipara@cune.edu>
 * Date:        2025-08-15
 * Description: Frontend Entrypoint
 */

import "vite/modulepreload-polyfill";
import "./app.css";
import "basecoat-css/all";
import htmx from "htmx.org";
import { Elm } from "./elm/Chat.elm";

window.htmx = htmx;

function scrollIntoView(elId) {
    const element = document.querySelector(`#${elId}`);
    if(!element) {
        setTimeout(() => {
            scrollIntoView(elId)
        }, 50);
    } else {
        element.scrollIntoView({ behavior: "smooth" });
    }
}

document.addEventListener("htmx:load", () => {
    const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    document.querySelectorAll('[data-chat]').forEach(node => {
        let app = Elm.Chat.init({
            node,
            flags: [
                parseInt(node.getAttribute("data-chat-bot-id")) ?? -1,
                node.getAttribute("data-chat-bot-name"),
                csrf
            ],
            document,
        });
        app.ports.scrollIntoView.subscribe(scrollIntoView);
        app.ports.createResponse.subscribe(([botId, promptId]) => {
            fetch(`/api/bots/${botId}/prompts/${promptId}/response/`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrf
                }
            }).then(res => {
                const reader = res.body.getReader()
                pump();
                function pump() {
                    reader.read().then(({ done, value }) => {
                        if (done) {
                            app.ports.recvResponseFinish.send(-1);
                            return;
                        }
                        const text = new TextDecoder("utf-8").decode(value);
                        app.ports.recvResponseChunk.send(text);
                        return pump();
                    })
                }
            })
        });
    })
});

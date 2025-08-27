port module Chat exposing (..)

import Browser
import Dict
import Html
import Html.Attributes exposing (class)
import Html.Events
import Http
import Json.Decode as D
import Json.Encode as E
import Time


type alias BotId =
    Int


type alias PromptId =
    Int


type alias ResponseId =
    Int


type alias Response =
    { body : String }


responseDecoder : D.Decoder Response
responseDecoder =
    D.map Response
        (D.field "body" D.string)


type alias Prompt =
    { id : PromptId
    , body : String
    , createdAt : Time.Posix
    , response : Maybe Response
    }


promptDecoder : D.Decoder Prompt
promptDecoder =
    D.map4 Prompt
        (D.field "id" D.int)
        (D.field "body" D.string)
        (D.field "createdAt" D.int |> D.map Time.millisToPosix)
        (D.field "response" (D.nullable responseDecoder))


type alias History =
    Dict.Dict Int Prompt


historyDecoder : D.Decoder History
historyDecoder =
    D.dict promptDecoder
        |> D.map
            (\x ->
                x
                    |> Dict.toList
                    |> List.filterMap (\( k, v ) -> String.toInt k |> Maybe.map (\ik -> ( ik, v )))
                    |> Dict.fromList
            )


orderPrompts : Prompt -> Prompt -> Order
orderPrompts p1 p2 =
    let
        result =
            Time.posixToMillis p1.createdAt - Time.posixToMillis p2.createdAt
    in
    if result > 0 then
        GT

    else if result < 0 then
        LT

    else
        EQ


type alias Model =
    { botId : BotId
    , botName : String
    , history : History
    , activeResponse : String
    , activePrompt : String
    , responseIsLoading : Bool
    , statusText : String
    , promptToRespondTo : Maybe Prompt
    , csrf : String
    }


type Msg
    = SetPrompt String
    | SubmitPrompt
    | GotPrompt (Result Http.Error Prompt)
    | GotHistory (Result Http.Error History)
    | GotResponseChunk String
    | FinishResponse


port recvResponseChunk : (String -> msg) -> Sub msg


port recvResponseFinish : (Int -> msg) -> Sub msg


port createResponse : ( BotId, Int ) -> Cmd msg


port scrollIntoView : String -> Cmd msg


updateHistory : History -> Maybe Prompt -> Response -> History
updateHistory history mprompt response =
    case mprompt of
        Nothing ->
            history

        Just prompt ->
            Dict.insert
                prompt.id
                { prompt | response = Just response }
                history


fetchHistory : Int -> Cmd Msg
fetchHistory botId =
    Http.get
        { url = "/api/bots/" ++ String.fromInt botId ++ "/history/"
        , expect = Http.expectJson GotHistory historyDecoder
        }


createPrompt : BotId -> String -> String -> Cmd Msg
createPrompt botId prompt csrf =
    Http.request
        { method = "POST"
        , url = "/api/bots/" ++ String.fromInt botId ++ "/prompts/"
        , body = Http.jsonBody (E.object [ ( "body", E.string prompt ) ])
        , expect = Http.expectJson GotPrompt promptDecoder
        , headers =
            [ Http.header "X-CSRFToken" csrf
            ]
        , timeout = Nothing
        , tracker = Nothing
        }


main : Program ( BotId, String, String ) Model Msg
main =
    Browser.element
        { init = init
        , view = view
        , update = update
        , subscriptions = subscriptions
        }


init : ( BotId, String, String ) -> ( Model, Cmd Msg )
init ( botId, botName, csrf ) =
    ( { botId = botId
      , botName = botName
      , history = Dict.empty
      , activeResponse = ""
      , activePrompt = ""
      , responseIsLoading = False
      , statusText = ""
      , promptToRespondTo = Nothing
      , csrf = csrf
      }
    , fetchHistory botId
    )


update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
    case msg of
        GotHistory r ->
            case r of
                Err _ ->
                    ( { model | statusText = "An error occured fetching history. Please refresh." }, Cmd.none )

                Ok h ->
                    ( { model | history = h }, scrollIntoView ("prompt" ++ String.fromInt (Dict.keys h |> List.reverse |> List.head |> Maybe.withDefault 0)) )

        SetPrompt s ->
            ( { model | activePrompt = s }, Cmd.none )

        SubmitPrompt ->
            ( { model
                | activePrompt = ""
                , responseIsLoading = True
                , history = Dict.insert -1 { id = -1, body = model.activePrompt, createdAt = Time.millisToPosix -1, response = Nothing } model.history
              }
            , Cmd.batch
                [ createPrompt model.botId model.activePrompt model.csrf
                , scrollIntoView "prompt-1"
                ]
            )

        GotPrompt r ->
            case r of
                Err _ ->
                    ( { model | statusText = "An error occured. Please resubmit the prompt." }, Cmd.none )

                Ok response ->
                    ( { model
                        | history = Dict.insert response.id response model.history
                        , promptToRespondTo = Just response
                      }
                    , Cmd.batch
                        [ createResponse ( model.botId, response.id )
                        , scrollIntoView ("prompt" ++ String.fromInt response.id)
                        ]
                    )

        GotResponseChunk chunk ->
            ( { model
                | activeResponse = model.activeResponse ++ chunk
              }
            , Cmd.none
            )

        FinishResponse ->
            ( { model
                | activeResponse = ""
                , history = updateHistory model.history model.promptToRespondTo { body = model.activeResponse }
                , promptToRespondTo = Nothing
                , responseIsLoading = False
              }
            , scrollIntoView ("response" ++ String.fromInt (model.promptToRespondTo |> Maybe.map .id |> Maybe.withDefault -1))
            )


subscriptions : Model -> Sub Msg
subscriptions _ =
    Sub.batch
        [ recvResponseChunk GotResponseChunk
        , recvResponseFinish (\_ -> FinishResponse)
        ]


view : Model -> Html.Html Msg
view model =
    Html.div [ class "mx-5" ]
        [ Html.div [ class "space-y-4 mt-5" ]
            [ Html.header [ class "flex items-center gap-2" ]
                [ Html.div [ class "flex flex-col gap-1 mr-auto" ]
                    [ Html.h3 [ class "text-3xl font-medium leading-none" ] [ Html.text (model.botName ++ " Chat") ]
                    ]
                ]
            , Html.section [ class "flex flex-col space-y-4 h-[70dvh] overflow-y-scroll" ]
                (model.history
                    |> Dict.values
                    |> List.sortWith orderPrompts
                    |> List.map
                        (\p ->
                            [ Html.div [ Html.Attributes.id ("prompt" ++ String.fromInt p.id), class "flex w-max max-w-[75%] flex-col gap-2 rounded-lg px-3 py-2 text-sm bg-primary text-primary-foreground ml-auto" ] [ Html.text p.body ]
                            , Html.div [ Html.Attributes.id ("response" ++ String.fromInt p.id), class "flex w-max max-w-[75%] flex-col gap-2 rounded-lg px-3 py-2 text-sm bg-muted" ]
                                [ Html.text
                                    (case p.response of
                                        Just response ->
                                            response.body

                                        Nothing ->
                                            if model.responseIsLoading && not (String.isEmpty model.activeResponse) then
                                                model.activeResponse

                                            else
                                                ""
                                    )
                                ]
                            ]
                        )
                    |> List.concat
                )
            , Html.div [ class "flex items-center space-x-2" ]
                [ Html.input
                    [ Html.Events.onInput SetPrompt
                    , class "input w-full"
                    , Html.Attributes.type_ "text"
                    , Html.Attributes.placeholder "Write a Message..."
                    , Html.Attributes.value model.activePrompt
                    ]
                    []
                , Html.button [ class "btn", Html.Attributes.type_ "submit", Html.Events.onClick SubmitPrompt ] [ Html.text "Submit" ]
                ]
            ]
        ]

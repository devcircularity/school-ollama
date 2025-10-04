// components/chat/ChatMessages.tsx - Complete file with enhanced markdown rendering
import React, { useEffect, useRef, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ChatBlockRenderer from './tools/ChatBlockRenderer';
import { Block, Action } from './tools/types';
import { Image, FileText, Download, ExternalLink, ThumbsUp, ThumbsDown } from 'lucide-react';
import { chatRatingService } from '@/services/chatRating';

interface FileAttachment {
  attachment_id: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  cloudinary_url: string;
  cloudinary_public_id: string;
  upload_timestamp: string;
  ocr_processed: boolean;
  ocr_data?: any;
}

interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  blocks?: Block[];
  intent?: string;
  rating?: number | null;
  response_data?: {
    blocks?: Block[];
    attachments?: FileAttachment[];
    [key: string]: any;
  };
}

interface ChatMessagesProps {
  messages: ChatMessage[];
  isLoading?: boolean;
  onAction?: (action: Action) => void;
  conversationId?: string;
}

// Component for rating buttons with conversation context
const MessageRating: React.FC<{ 
  messageId: string;
  conversationId: string;
  initialRating?: number | null;
  onRatingChange?: (rating: number) => void;
}> = ({ messageId, conversationId, initialRating, onRatingChange }) => {
  const [rating, setRating] = useState<number | null>(initialRating ?? null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRating(initialRating ?? null);
  }, [initialRating]);

  const handleRate = async (newRating: 1 | -1) => {
    if (rating === newRating) return;
    
    setIsSubmitting(true);
    setError(null);

    try {
      await chatRatingService.rateMessageInConversation(conversationId, messageId, newRating);
      setRating(newRating);
      onRatingChange?.(newRating);
      
      console.log(`Successfully rated message ${messageId} with ${newRating}`);
    } catch (error: any) {
      console.error('Failed to rate message:', error);
      setError(error.message || 'Failed to submit rating');
      
      setTimeout(() => {
        setError(null);
      }, 3000);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex items-center gap-2 mt-3">
      <div className="flex items-center gap-1">
        <button
          onClick={() => handleRate(1)}
          disabled={isSubmitting}
          className={`p-2 rounded-lg transition-all duration-200 disabled:opacity-50 ${
            rating === 1
              ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
              : 'hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500 hover:text-green-600 dark:text-neutral-400 dark:hover:text-green-400'
          }`}
          title={rating === 1 ? 'You liked this response' : 'Rate this response positively'}
        >
          <ThumbsUp size={14} className={rating === 1 ? 'fill-current' : ''} />
        </button>

        <button
          onClick={() => handleRate(-1)}
          disabled={isSubmitting}
          className={`p-2 rounded-lg transition-all duration-200 disabled:opacity-50 ${
            rating === -1
              ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'
              : 'hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500 hover:text-red-600 dark:text-neutral-400 dark:hover:text-red-400'
          }`}
          title={rating === -1 ? 'You disliked this response' : 'Rate this response negatively'}
        >
          <ThumbsDown size={14} className={rating === -1 ? 'fill-current' : ''} />
        </button>
      </div>

      {isSubmitting && (
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 border border-neutral-300 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-xs text-neutral-500">Rating...</span>
        </div>
      )}

      {error && (
        <span className="text-xs text-red-500">{error}</span>
      )}

      {rating !== null && !isSubmitting && !error && (
        <span className="text-xs text-neutral-500">
          {rating === 1 ? 'Thanks for the feedback!' : 'Feedback received'}
        </span>
      )}
    </div>
  );
};

const ChatMessages: React.FC<ChatMessagesProps> = ({ 
  messages, 
  isLoading = false, 
  onAction,
  conversationId 
}) => {
  const params = useParams<{ chatId: string }>();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [lastUserMessageIndex, setLastUserMessageIndex] = useState<number | null>(null);
  const [preventScrolling, setPreventScrolling] = useState(false);
  
  const messageSignature = useMemo(() => {
    return messages.map(msg => ({
      id: msg.id,
      role: msg.role,
      content: msg.content.slice(0, 50),
      timestamp: msg.timestamp
    }));
  }, [messages]);
  
  const previousSignature = useRef<typeof messageSignature>([]);
  const [localRatings, setLocalRatings] = useState<Record<string, number>>({});

  const currentConversationId = conversationId || params.chatId;

  useEffect(() => {
    if (currentConversationId && currentConversationId !== 'new') {
      chatRatingService.setCurrentConversation(currentConversationId);
    }
    
    return () => {
      chatRatingService.clearCurrentConversation();
    };
  }, [currentConversationId]);

  useEffect(() => {
    const currentSignature = messageSignature;
    const previousSig = previousSignature.current;
    
    if (isInitialLoad && currentSignature.length > 0) {
      setTimeout(() => {
        scrollToBottom();
        setIsInitialLoad(false);
        previousSignature.current = currentSignature;
      }, 100);
      return;
    }
    
    if (preventScrolling) {
      previousSignature.current = currentSignature;
      return;
    }
    
    const isReallyNewMessages = currentSignature.length > previousSig.length && 
      currentSignature.slice(0, previousSig.length).every((msg, idx) => 
        msg.id === previousSig[idx]?.id && 
        msg.content === previousSig[idx]?.content
      );
    
    if (isReallyNewMessages && !isInitialLoad) {
      const newMessagesCount = currentSignature.length - previousSig.length;
      const lastMessage = messages[messages.length - 1];
      
      console.log(`ChatMessages: Detected ${newMessagesCount} new message(s), last message role: ${lastMessage?.role}`);
      
      if (lastMessage?.role === 'user') {
        setLastUserMessageIndex(messages.length - 1);
        setTimeout(() => {
          scrollToUserMessage(messages.length - 1);
        }, 100);
      } else if (lastMessage?.role === 'assistant' && lastUserMessageIndex !== null) {
        setTimeout(() => {
          scrollToUserMessage(lastUserMessageIndex);
          setLastUserMessageIndex(null);
        }, 150);
      } else {
        scrollToBottom();
      }
    }
    
    previousSignature.current = currentSignature;
  }, [messageSignature, isInitialLoad, preventScrolling, lastUserMessageIndex, messages]);

  const scrollToBottom = () => {
    const container = scrollContainerRef.current;
    if (container) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
  };

  const scrollToUserMessage = (userMessageIndex: number) => {
    const container = scrollContainerRef.current;
    const messagesContainer = messagesContainerRef.current;
    
    if (!container || !messagesContainer) return;
    
    const userMessageElement = messagesContainer.querySelector(
      `[data-message-index="${userMessageIndex}"]`
    ) as HTMLElement;
    
    if (userMessageElement) {
      const header = document.querySelector('header');
      const headerHeight = header ? header.getBoundingClientRect().height : 60;
      const paddingBelowHeader = 24;
      const totalOffset = headerHeight + paddingBelowHeader;
      
      const userMessageRect = userMessageElement.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      
      const currentScrollTop = container.scrollTop;
      const messageTopRelativeToContainer = userMessageRect.top - containerRect.top;
      const targetScrollTop = currentScrollTop + messageTopRelativeToContainer - totalOffset;
      
      console.log(`ChatMessages: Scrolling to position user message ${userMessageIndex} with offset ${totalOffset}px`);
      
      container.scrollTo({
        top: Math.max(0, targetScrollTop),
        behavior: 'smooth'
      });
    }
  };

  const handleBlockAction = async (action: Action) => {
    console.log('Block action triggered:', action);
    
    if (onAction) {
      await onAction(action);
      return;
    }

    switch (action.type) {
      case 'query':
        console.log('Query action:', action.payload);
        break;
        
      case 'route':
        if (action.target) {
          window.location.href = action.target;
        }
        break;
        
      case 'download':
        if (action.endpoint) {
          const link = document.createElement('a');
          link.href = action.endpoint;
          if (action.payload?.filename) {
            link.download = action.payload.filename;
          }
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }
        break;
        
      case 'mutation':
        if (action.endpoint) {
          try {
            const response = await fetch(action.endpoint, {
              method: action.method || 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`,
                'X-School-ID': localStorage.getItem('schoolId') || ''
              },
              body: action.payload ? JSON.stringify(action.payload) : undefined
            });
            
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
            }
            
            console.log('Mutation successful');
          } catch (error) {
            console.error('Mutation failed:', error);
          }
        }
        break;
        
      default:
        console.warn('Unhandled action type:', action.type);
    }
  };

  const handleRatingChange = (messageId: string, rating: number) => {
    setPreventScrolling(true);
    
    setLocalRatings(prev => ({
      ...prev,
      [messageId]: rating
    }));
    
    setTimeout(() => {
      setPreventScrolling(false);
    }, 500);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const isImageFile = (contentType: string): boolean => {
    return contentType.startsWith('image/');
  };

  const FileAttachments: React.FC<{ attachments: FileAttachment[] }> = ({ attachments }) => {
    const [previewImage, setPreviewImage] = useState<string | null>(null);
    
    if (!attachments || attachments.length === 0) {
      return null;
    }

    const openImagePreview = (imageUrl: string) => {
      setPreviewImage(imageUrl);
    };

    const closeImagePreview = () => {
      setPreviewImage(null);
    };

    return (
      <>
        <div className="flex flex-wrap gap-2 justify-end">
          {attachments.map((attachment, index) => (
            <div
              key={attachment.attachment_id || index}
              className="relative group cursor-pointer"
              onClick={() => {
                if (isImageFile(attachment.content_type)) {
                  openImagePreview(attachment.cloudinary_url);
                } else {
                  window.open(attachment.cloudinary_url, '_blank');
                }
              }}
            >
              {isImageFile(attachment.content_type) ? (
                <div className="w-32 h-24 xs:w-40 xs:h-28 sm:w-48 sm:h-32 md:w-56 md:h-36 lg:w-64 lg:h-40 rounded-lg overflow-hidden border border-neutral-300 dark:border-neutral-600 hover:border-neutral-400 dark:hover:border-neutral-500 transition-colors">
                  <img
                    src={attachment.cloudinary_url}
                    alt={attachment.original_filename}
                    className="w-full h-full object-cover"
                  />
                </div>
              ) : (
                <div className="w-24 h-24 xs:w-28 xs:h-28 sm:w-32 sm:h-32 md:w-36 md:h-36 lg:w-40 lg:h-40 rounded-lg bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 hover:border-neutral-400 dark:hover:border-neutral-500 transition-colors flex flex-col items-center justify-center">
                  <FileText size={24} className="xs:w-6 xs:h-6 sm:w-8 sm:h-8 text-neutral-500 dark:text-neutral-400 mb-2" />
                  <span className="text-xs text-neutral-600 dark:text-neutral-400 font-medium">
                    {attachment.content_type === 'application/pdf' ? 'PDF' : 'DOC'}
                  </span>
                </div>
              )}
              
              <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-30 transition-all duration-200 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100">
                <div className="flex gap-1 xs:gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isImageFile(attachment.content_type)) {
                        openImagePreview(attachment.cloudinary_url);
                      } else {
                        window.open(attachment.cloudinary_url, '_blank');
                      }
                    }}
                    className="p-1.5 xs:p-2 bg-white dark:bg-neutral-800 rounded-full shadow-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                    title="View"
                  >
                    <ExternalLink size={12} className="xs:w-3.5 xs:h-3.5 text-neutral-700 dark:text-neutral-300" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      const link = document.createElement('a');
                      link.href = attachment.cloudinary_url;
                      link.download = attachment.original_filename;
                      document.body.appendChild(link);
                      link.click();
                      document.body.removeChild(link);
                    }}
                    className="p-1.5 xs:p-2 bg-white dark:bg-neutral-800 rounded-full shadow-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
                    title="Download"
                  >
                    <Download size={12} className="xs:w-3.5 xs:h-3.5 text-neutral-700 dark:text-neutral-300" />
                  </button>
                </div>
              </div>

              {attachment.ocr_processed && (
                <div className="absolute top-1 right-1 xs:top-2 xs:right-2 w-1.5 h-1.5 xs:w-2 xs:h-2 bg-green-500 rounded-full shadow-sm" title="OCR Processed"></div>
              )}
            </div>
          ))}
        </div>

        {previewImage && (
          <div 
            className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
            onClick={closeImagePreview}
          >
            <div className="relative max-w-full max-h-full w-full h-full flex items-center justify-center">
              <img
                src={previewImage}
                alt="Preview"
                className="max-w-full max-h-full object-contain rounded-lg"
                onClick={(e) => e.stopPropagation()}
              />
              <button
                onClick={closeImagePreview}
                className="absolute top-4 right-4 w-10 h-10 bg-black bg-opacity-50 hover:bg-opacity-75 text-white rounded-full flex items-center justify-center transition-colors"
                title="Close"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
          </div>
        )}
      </>
    );
  };

  const renderMessage = (message: ChatMessage, index: number) => {
    const isUser = message.role === 'user';

    let blocksToRender: Block[] = [];
    if (!isUser) {
      if (message.blocks && message.blocks.length > 0) {
        blocksToRender = message.blocks;
      } else if (message.response_data?.blocks && message.response_data.blocks.length > 0) {
        blocksToRender = message.response_data.blocks;
      }
    }

    let attachments: FileAttachment[] | null = null;
    if (isUser && message.response_data?.attachments) {
      attachments = message.response_data.attachments;
    }

    const messageKey = message.id || `${message.role}-${index}`;
    const currentRating = localRatings[message.id!] ?? message.rating ?? null;

    return (
      <div 
        key={messageKey} 
        className={`mb-6 xs:mb-8 ${isUser ? 'flex justify-end' : ''}`}
        data-message-index={index}
      >
        <div className={`w-full ${isUser ? 'max-w-full xs:max-w-md sm:max-w-lg md:max-w-xl lg:max-w-2xl' : 'max-w-full'}`}>
          
          {isUser ? (
            <div className="space-y-3 w-full">
              <div className="flex flex-col items-end space-y-3 w-full">
                {attachments && attachments.length > 0 && (
                  <div className="flex justify-end w-full">
                    <div className="max-w-full overflow-hidden">
                      <div className="flex justify-end">
                        <FileAttachments attachments={attachments} />
                      </div>
                    </div>
                  </div>
                )}
                
                <div className="inline-block rounded-2xl px-3 xs:px-4 py-2 xs:py-3 text-white max-w-full break-words" 
                     style={{ backgroundColor: 'var(--color-brand)' }}>
                  <div className="text-sm xs:text-[15px] leading-relaxed">
                    {message.content}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-3 xs:space-y-4 w-full">
              
              {message.content && (
                <div className="prose prose-sm max-w-none dark:prose-invert break-words">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({children}) => (
                        <h1 className="text-xl xs:text-2xl font-bold mb-3 xs:mb-4 text-neutral-900 dark:text-neutral-100 border-b border-neutral-200 dark:border-neutral-700 pb-2">
                          {children}
                        </h1>
                      ),
                      h2: ({children}) => (
                        <h2 className="text-lg xs:text-xl font-bold mb-2 xs:mb-3 text-neutral-900 dark:text-neutral-100">
                          {children}
                        </h2>
                      ),
                      h3: ({children}) => (
                        <h3 className="text-base xs:text-lg font-semibold mb-2 text-neutral-900 dark:text-neutral-100">
                          {children}
                        </h3>
                      ),
                      h4: ({children}) => (
                        <h4 className="text-sm xs:text-base font-semibold mb-2 text-neutral-800 dark:text-neutral-200">
                          {children}
                        </h4>
                      ),
                      p: ({children}) => (
                        <p className="mb-3 leading-relaxed text-neutral-900 dark:text-neutral-100 break-words">
                          {children}
                        </p>
                      ),
                      strong: ({children}) => (
                        <strong className="font-bold text-neutral-900 dark:text-neutral-100">
                          {children}
                        </strong>
                      ),
                      em: ({children}) => (
                        <em className="italic text-neutral-800 dark:text-neutral-200">
                          {children}
                        </em>
                      ),
                      code: ({inline, children, className, ...props}: any) => {
                        if (inline) {
                          return (
                            <code 
                              className="bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-xs xs:text-sm font-mono text-red-600 dark:text-red-400"
                              {...props}
                            >
                              {children}
                            </code>
                          );
                        }
                        return (
                          <pre className="bg-neutral-900 dark:bg-neutral-950 rounded-lg p-4 overflow-x-auto my-3">
                            <code 
                              className="text-sm font-mono text-neutral-100 dark:text-neutral-200 block"
                              style={{ 
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                              }}
                            >
                              {String(children).replace(/\n$/, '')}
                            </code>
                          </pre>
                        );
                      },
                      ul: ({children}) => (
                        <ul className="list-disc list-outside ml-5 mb-3 space-y-1 text-neutral-900 dark:text-neutral-100 break-words">
                          {children}
                        </ul>
                      ),
                      ol: ({children}) => (
                        <ol className="list-decimal list-outside ml-5 mb-3 space-y-1 text-neutral-900 dark:text-neutral-100 break-words">
                          {children}
                        </ol>
                      ),
                      li: ({children}) => (
                        <li className="leading-relaxed text-neutral-900 dark:text-neutral-100 break-words pl-1">
                          {children}
                        </li>
                      ),
                      a: ({href, children}) => (
                        <a 
                          href={href} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline"
                        >
                          {children}
                        </a>
                      ),
                      blockquote: ({children}) => (
                        <blockquote className="border-l-4 border-neutral-300 dark:border-neutral-600 pl-4 py-2 my-3 italic text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-800/50 rounded-r">
                          {children}
                        </blockquote>
                      ),
                      hr: () => (
                        <hr className="my-4 border-neutral-200 dark:border-neutral-700" />
                      ),
                      table: ({children}) => (
                        <div className="overflow-x-auto my-3">
                          <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700 border border-neutral-200 dark:border-neutral-700 rounded-lg">
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({children}) => (
                        <thead className="bg-neutral-50 dark:bg-neutral-800">
                          {children}
                        </thead>
                      ),
                      tbody: ({children}) => (
                        <tbody className="bg-white dark:bg-neutral-900 divide-y divide-neutral-200 dark:divide-neutral-700">
                          {children}
                        </tbody>
                      ),
                      tr: ({children}) => (
                        <tr>{children}</tr>
                      ),
                      th: ({children}) => (
                        <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-700 dark:text-neutral-300 uppercase tracking-wider">
                          {children}
                        </th>
                      ),
                      td: ({children}) => (
                        <td className="px-4 py-2 text-sm text-neutral-900 dark:text-neutral-100">
                          {children}
                        </td>
                      ),
                    }}
                  >
                    {message.content}
                  </ReactMarkdown>
                </div>
              )}
              
              {blocksToRender.length > 0 && (
                <div className="space-y-3 xs:space-y-4 w-full overflow-hidden">
                  <ChatBlockRenderer 
                    blocks={blocksToRender} 
                    onAction={handleBlockAction}
                  />
                </div>
              )}

              {!isUser && message.id && currentConversationId && currentConversationId !== 'new' && (
                <MessageRating
                  messageId={message.id}
                  conversationId={currentConversationId}
                  initialRating={currentRating}
                  onRatingChange={(rating) => handleRatingChange(message.id!, rating)}
                />
              )}
            </div>
          )}
          
          {message.intent && !isUser && (
            <div className="text-xs text-neutral-400 mt-2 text-left break-words">
              • {message.intent}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div 
      ref={scrollContainerRef}
      className="flex-1 overflow-y-auto overflow-x-hidden h-full"
      style={{ 
        height: '100%',
        maxHeight: '100%'
      }}
    >
      <div 
        ref={messagesContainerRef}
        className="min-h-full px-3 xs:px-4 sm:px-6 pt-4 pb-6 xs:pb-8 w-full"
      >
        <div className="max-w-4xl mx-auto w-full">
          {messages.map(renderMessage)}
          
          {isLoading && (
            <div className="mb-4 xs:mb-6">
              <div className="max-w-4xl w-full">
                <div className="flex items-center space-x-2 text-neutral-500">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                    <div className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                  </div>
                  <span className="text-xs xs:text-sm">AI is thinking...</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatMessages;
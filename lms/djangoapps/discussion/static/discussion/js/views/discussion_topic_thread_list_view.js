(function(define) {
    'use strict';

    define([
        'underscore',
        'backbone',
        'edx-ui-toolkit/js/utils/html-utils',
        'text!discussion/templates/topic-thread-list.underscore'
    ],
    function(_, Backbone, HtmlUtils, threadListTemplate) {
        var discussionTopicThreadListView = Backbone.View.extend({
            events: {
                //'topic:selected': 'renderThreads'
            },
            initialize: function(options) {
                this.displayedCollection = new Discussion(this.collection.models, {
                    pages: this.collection.pages
                });

                
                //this.threadListView = options.threadListView;
                this.listenTo(this.model, 'change', this.render);
                this.render();
            },
            render: function() {
                HtmlUtils.setHtml(this.$('.forum-nav-thread-list'), HtmlUtils.template(threadListTemplate)({
                     threads: this.displayedCollection.models
                }));
                return this;
            },
            renderEachThreadList: function(thread) {
                var threadCommentCount = thread.get('comments_count'),
                    threadUnreadCommentCount = thread.get('unread_comments_count'),
                    neverRead = !thread.get('read') && threadUnreadCommentCount === threadCommentCount,
                    context = _.extend(
                        {
                            neverRead: neverRead,
                            threadUrl: thread.urlFor('retrieve')
                        },
                        thread.toJSON()
                    );console.log(context.thread);
                return $(this.template(context.thread).toString());
            }
        });

        return discussionTopicThreadListView;
    });
}).call(this, define || RequireJS.define);

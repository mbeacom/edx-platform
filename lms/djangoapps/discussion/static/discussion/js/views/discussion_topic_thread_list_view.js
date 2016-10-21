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
                //'topic:selected': 'clearSearch'
            },
            initialize: function(options) {
                _.extend(this, _.pick(options, 'threadListView'));

                this.template = HtmlUtils.template(threadListTemplate);
                this.threadListView = options.threadListView;

                this.listenTo(this.model, 'change', this.render);
                this.render();
            },
            render: function() {
                HtmlUtils.setHtml(this.$el, this.template());
                return this;
            }
        });

        return discussionTopicThreadListView;
    });
}).call(this, define || RequireJS.define);

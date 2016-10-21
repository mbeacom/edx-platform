(function(define) {
    'use strict';

    define([
        'underscore',
        'backbone',
        'edx-ui-toolkit/js/utils/html-utils',
        'common/js/discussion/utils',
        'text!discussion/templates/topic-thread-list.underscore',
        'text!discussion/templates/discussion-home.underscore'
    ],
    function(_, Backbone, HtmlUtils, DiscussionUtil, threadListTemplate, discussionHomeTemplate) {
        var DiscussionBoardView = Backbone.View.extend({
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
                // HtmlUtils.setHtml(this.$('.forum-nav-thread-list'), HtmlUtils.template(threadListTemplate)({
                //      threads: this.displayedCollection.models
                // }));
                $(window).bind('load scroll resize', this.updateSidebar);
                this.showBrowseMenu(true);
                return this;
            },

            isBrowseMenuVisible: function() {
                return this.$('.forum-nav-browse-menu-wrapper').is(':visible');
            },

            showBrowseMenu: function(initialLoad) {
                if (!this.isBrowseMenuVisible()) {
                    this.$('.forum-nav-browse-menu-wrapper').show();
                    this.$('.forum-nav-thread-list-wrapper').hide();
                    if (!initialLoad) {
                        $('.forum-nav-browse-filter-input').focus();
                        this.filterInputReset();
                    }
                    $('body').bind('click', _.bind(this.hideBrowseMenu, this));
                    this.updateSidebar();
                }
            },

            hideBrowseMenu: function() {
                var selectedTopicList = this.$('.forum-nav-browse-title.is-focused');
                if (this.isBrowseMenuVisible()) {
                    selectedTopicList.removeClass('is-focused');
                    this.$('.forum-nav-browse-menu-wrapper').hide();
                    this.$('.forum-nav-thread-list-wrapper').show();
                    if (this.selectedTopicId !== 'undefined') {
                        this.$('.forum-nav-browse-filter-input').attr('aria-activedescendant', this.selectedTopicId);
                    }
                    $('body').unbind('click', this.hideBrowseMenu);
                    this.updateSidebar();
                }
            },

            toggleBrowseMenu: function(event) {
                var inputText = $('.forum-nav-browse-filter-input').val();
                event.preventDefault();
                event.stopPropagation();
                if (this.isBrowseMenuVisible()) {
                    this.hideBrowseMenu();
                } else {
                    if (inputText !== '') {
                        this.filterTopics(inputText);
                    }
                    this.showBrowseMenu();
                }
            },

            updateSidebar: function() {
                var amount, browseFilterHeight, discussionBody, discussionBottomOffset, discussionsBodyBottom,
                    discussionsBodyTop, headerHeight, refineBarHeight, scrollTop, sidebar, sidebarHeight, topOffset,
                    windowHeight, $discussionBody, $sidebar;
                scrollTop = $(window).scrollTop();
                windowHeight = $(window).height();
                $discussionBody = this.$('.discussion-column');
                discussionsBodyTop = $discussionBody[0] ? $discussionBody.offset().top : void 0;
                discussionsBodyBottom = discussionsBodyTop + $discussionBody.outerHeight();
                $sidebar = this.$('.forum-nav');
                if (scrollTop > discussionsBodyTop - this.sidebar_padding) {
                    $sidebar.css('top', scrollTop - discussionsBodyTop + this.sidebar_padding);
                } else {
                    $sidebar.css('top', '0');
                }
                sidebarHeight = windowHeight - Math.max(discussionsBodyTop - scrollTop, this.sidebar_padding);
                topOffset = scrollTop + windowHeight;
                discussionBottomOffset = discussionsBodyBottom + this.sidebar_padding;
                amount = Math.max(topOffset - discussionBottomOffset, 0);
                sidebarHeight = sidebarHeight - this.sidebar_padding - amount;
                sidebarHeight = Math.min(sidebarHeight + 1, $discussionBody.outerHeight());
                $sidebar.css('height', sidebarHeight);
                headerHeight = this.$('.forum-nav-header').outerHeight();
                refineBarHeight = this.$('.forum-nav-refine-bar').outerHeight();
                browseFilterHeight = this.$('.forum-nav-browse-filter').outerHeight();
                this.$('.forum-nav-thread-list')
                    .css('height', (sidebarHeight - headerHeight - refineBarHeight - 2) + 'px');
                this.$('.forum-nav-browse-menu')
                    .css('height', (sidebarHeight - headerHeight - browseFilterHeight - 2) + 'px');
            },

            // TODO: move this to the router?
            goHome: function() {
                // var url;
                HtmlUtils.append(this.$('.forum-content').empty(), HtmlUtils.template(discussionHomeTemplate)({}));
                // $('.forum-nav-thread-list a').removeClass('is-active').find('.sr')
                //     .remove();
                // $('input.email-setting').bind('click', this.updateEmailNotifications);
                // url = DiscussionUtil.urlFor('notifications_status', window.user.get('id'));
                // DiscussionUtil.safeAjax({
                //     url: url,
                //     type: 'GET',
                //     success: function(response) {
                //         $('input.email-setting').prop('checked', response.status);
                //     }
                // });
            }
       });

        return DiscussionBoardView;
    });
}).call(this, define || RequireJS.define);

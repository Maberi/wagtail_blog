import datetime

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from wagtail.contrib.search_promotions.models import Query
from wagtail.snippets.models import register_snippet
from taggit.models import Tag

from .abstract import (
    BlogCategoryAbstract,
    BlogCategoryBlogPageAbstract,
    BlogIndexPageAbstract,
    BlogPageAbstract,
    BlogPageTagAbstract
)

COMMENTS_APP = getattr(settings, 'COMMENTS_APP', None)


class BlogIndexPage(BlogIndexPageAbstract):
    class Meta:
        verbose_name = _('Blog index')

    @property
    def blogs(self):
        # Get list of blog pages that are descendants of this page
        blogs = BlogPage.objects.descendant_of(self).live()
        blogs = blogs.order_by(
            '-date'
        ).select_related('owner').prefetch_related(
            'tagged_items__tag',
            'categories',
            'categories__category',
        )
        return blogs

    def get_context(self, request, tag=None, category=None, author=None, from_date=None, to_date=None,
                    search_query=None, *args, **kwargs):
        context = super(BlogIndexPage, self).get_context(
            request, *args, **kwargs)
        blogs = self.blogs

        if tag is None:
            tag = request.GET.get('tag')
        if tag:
            blogs = blogs.filter(tags__slug=tag)
        if category is None:  # Not coming from category_view in views.py
            if request.GET.get('category'):
                category = get_object_or_404(
                    BlogCategory, slug=request.GET.get('category'))
        if category:
            if not request.GET.get('category'):
                category = get_object_or_404(BlogCategory, slug=category)
            blogs = blogs.filter(categories__category__name=category)
        if author:
            if isinstance(author, str) and not author.isdigit():
                blogs = blogs.filter(author__username=author)
            else:
                blogs = blogs.filter(author_id=author)
        if from_date is None:
            from_date = request.GET.get('from_date')
        if to_date is None:
            to_date = request.GET.get('to_date')
        try:
            q = ~Q(pk__in=[])
            if to_date:
                fecha = datetime.datetime.strptime(to_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                q = q & Q(date__lte=fecha)
                context['to_date'] = fecha
            if from_date:
                fecha = datetime.datetime.strptime(from_date, '%Y-%m-%d')
                q = q & Q(date__gte=fecha)
                context['from_date'] = fecha
            blogs = blogs.filter(q)
        except ValueError:
            pass

        # Search
        if search_query is None:
            search_query = request.GET.get('query', None)
        if search_query:
            blogs = blogs.search(search_query)
            query = Query.get(search_query)

            # Record hit
            query.add_hit()

        # Pagination
        page = request.GET.get('page')
        page_size = 10
        if hasattr(settings, 'BLOG_PAGINATION_PER_PAGE'):
            page_size = settings.BLOG_PAGINATION_PER_PAGE

        paginator = None
        if page_size is not None:
            paginator = Paginator(blogs, page_size)  # Show 10 blogs per page
            try:
                blogs = paginator.page(page)
            except PageNotAnInteger:
                blogs = paginator.page(1)
            except EmptyPage:
                blogs = paginator.page(paginator.num_pages)

        context['blogs'] = blogs
        context['category'] = category
        context['tag'] = tag
        context['author'] = author
        context['COMMENTS_APP'] = COMMENTS_APP
        context['paginator'] = paginator
        context['search_query'] = search_query
        context = get_blog_context(context)

        return context

    subpage_types = ['blog.BlogPage']


@register_snippet
class BlogCategory(BlogCategoryAbstract):
    class Meta:
        ordering = ['name']
        verbose_name = _("Blog Category")
        verbose_name_plural = _("Blog Categories")


class BlogCategoryBlogPage(BlogCategoryBlogPageAbstract):
    class Meta:
        pass


class BlogPageTag(BlogPageTagAbstract):
    class Meta:
        pass


@register_snippet
class BlogTag(Tag):
    class Meta:
        proxy = True


def get_blog_context(context):
    """ Get context data useful on all blog related pages """
    context['authors'] = get_user_model().objects.filter(
        owned_pages__live=True,
        owned_pages__content_type__model='blogpage'
    ).annotate(Count('owned_pages')).order_by('-owned_pages__count')
    context['all_categories'] = BlogCategory.objects.all()
    context['root_categories'] = BlogCategory.objects.filter(
        parent=None,
    ).prefetch_related(
        'children',
    ).annotate(
        blog_count=Count('blogpage'),
    )
    return context


class BlogPage(BlogPageAbstract):
    class Meta:
        verbose_name = _('Blog page')
        verbose_name_plural = _('Blog pages')

    def get_blog_index(self):
        # Find closest ancestor which is a blog index
        return self.get_ancestors().type(BlogIndexPage).last()

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context['blogs'] = self.get_blog_index().blogindexpage.blogs
        context = get_blog_context(context)
        context['COMMENTS_APP'] = COMMENTS_APP
        return context

    parent_page_types = ['blog.BlogIndexPage']
